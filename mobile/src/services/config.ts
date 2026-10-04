export const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "https://api.diaglob.tech"
).replace(/\/$/, "");

export const AWS_REGION =
  process.env.EXPO_PUBLIC_AWS_REGION || "us-east-2";

export const COGNITO_CLIENT_ID =
  process.env.EXPO_PUBLIC_COGNITO_CLIENT_ID ||
  "7gas2mvvovukjpk05jhbku4303";

export const COGNITO_ENDPOINT =
  `https://cognito-idp.${AWS_REGION}.amazonaws.com/`;
