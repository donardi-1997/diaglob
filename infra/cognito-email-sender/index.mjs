import { KmsKeyringNode, buildClient, CommitmentPolicy } from "@aws-crypto/client-node";
import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";
import nodemailer from "nodemailer";

const { decrypt } = buildClient(CommitmentPolicy.REQUIRE_ENCRYPT_ALLOW_DECRYPT);

const REGION = process.env.AWS_REGION || "us-east-2";
const KEY_ID = process.env.KEY_ID;
const KEY_ARN = process.env.KEY_ARN;
const SMTP_SECRET_ID = process.env.SMTP_SECRET_ID || "/diaglob/prod/spacemail-smtp";
const APP_URL = process.env.APP_URL || "https://diaglob.tech";

const secrets = new SecretsManagerClient({ region: REGION });
let cachedSmtp;

async function getSmtpConfig() {
  if (cachedSmtp) return cachedSmtp;

  const response = await secrets.send(
    new GetSecretValueCommand({ SecretId: SMTP_SECRET_ID }),
  );

  if (!response.SecretString) {
    throw new Error("SMTP secret has no SecretString");
  }

  cachedSmtp = JSON.parse(response.SecretString);
  return cachedSmtp;
}

async function decryptCode(encryptedCode) {
  if (!KEY_ID || !KEY_ARN) {
    throw new Error("Missing KEY_ID/KEY_ARN");
  }

  const keyring = new KmsKeyringNode({
    generatorKeyId: KEY_ID,
    keyIds: [KEY_ARN],
  });

  const ciphertext = Buffer.from(encryptedCode, "base64");
  const { plaintext } = await decrypt(keyring, ciphertext);
  return plaintext.toString("utf8");
}

function subjectFor(triggerSource) {
  if (triggerSource.includes("ForgotPassword")) return "Restablece tu contraseña de DIAGLOB";
  if (triggerSource.includes("UpdateUserAttribute")) return "Confirma tu nuevo correo en DIAGLOB";
  return "Confirma tu cuenta de DIAGLOB";
}

function headingFor(triggerSource) {
  if (triggerSource.includes("ForgotPassword")) return "Restablece tu contraseña";
  if (triggerSource.includes("UpdateUserAttribute")) return "Confirma tu nuevo correo";
  return "Confirma tu cuenta";
}

function descriptionFor(triggerSource) {
  if (triggerSource.includes("ForgotPassword")) {
    return "Usa este código para continuar con el cambio de contraseña de tu cuenta.";
  }

  if (triggerSource.includes("UpdateUserAttribute")) {
    return "Usa este código para verificar tu nuevo correo y mantener tu cuenta segura.";
  }

  return "Usa este código para verificar tu correo y terminar de crear tu espacio de trabajo en DIAGLOB.";
}

function buildHtml({ code, triggerSource }) {
  const heading = headingFor(triggerSource);
  const description = descriptionFor(triggerSource);

  return `<!doctype html>
<html lang="es">
  <body style="margin:0;background:#070b14;font-family:Inter,Arial,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#070b14;padding:36px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border-radius:24px;overflow:hidden;">
            <tr>
              <td style="padding:30px 36px;background:linear-gradient(135deg,#111827,#4f46e5);color:#fff;">
                <div style="font-size:13px;letter-spacing:3px;font-weight:700;opacity:.78;">DIAGLOB</div>
                <div style="font-size:28px;font-weight:800;margin-top:8px;">AI COMMERCE OS</div>
              </td>
            </tr>
            <tr>
              <td style="padding:42px 36px 14px;">
                <div style="font-size:13px;font-weight:800;color:#7c3aed;text-transform:uppercase;letter-spacing:1.4px;">Acceso seguro</div>
                <h1 style="margin:10px 0 12px;font-size:30px;line-height:1.15;color:#111827;">${heading}</h1>
                <p style="margin:0;color:#64748b;font-size:16px;line-height:1.65;">${description}</p>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:18px 36px 24px;">
                <div style="display:inline-block;background:#f5f3ff;border:1px solid #ddd6fe;border-radius:18px;padding:20px 26px;font-size:34px;letter-spacing:10px;font-weight:800;color:#4f46e5;">
                  ${code}
                </div>
                <div style="margin-top:14px;color:#94a3b8;font-size:13px;">Este código expira automáticamente.</div>
              </td>
            </tr>
            <tr>
              <td style="padding:4px 36px 36px;">
                <div style="border-top:1px solid #e2e8f0;padding-top:24px;color:#64748b;font-size:13px;line-height:1.6;">
                  Si no solicitaste este código, puedes ignorar este mensaje de forma segura.
                  <br><br>
                  <a href="${APP_URL}" style="color:#4f46e5;text-decoration:none;font-weight:700;">diaglob.tech</a>
                </div>
              </td>
            </tr>
          </table>
          <div style="max-width:600px;color:#64748b;font-size:12px;line-height:1.6;padding:18px 8px;">
            © DIAGLOB · Vende más. Trabaja menos.
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>`;
}

export const handler = async (event) => {
  const email = event?.request?.userAttributes?.email;
  const encryptedCode = event?.request?.code;
  const triggerSource = event?.triggerSource || "CustomEmailSender_SignUp";

  if (!email || !encryptedCode) {
    throw new Error("CustomEmailSender event is missing email or code");
  }

  const code = await decryptCode(encryptedCode);
  const smtp = await getSmtpConfig();

  const transporter = nodemailer.createTransport({
    host: smtp.host || "mail.spacemail.com",
    port: Number(smtp.port || 465),
    secure: true,
    auth: {
      user: smtp.username,
      pass: smtp.password,
    },
  });

  await transporter.sendMail({
    from: smtp.from || `DIAGLOB <${smtp.username}>`,
    replyTo: smtp.reply_to || smtp.username,
    to: email,
    subject: subjectFor(triggerSource),
    html: buildHtml({ code, triggerSource }),
  });

  return event;
};
