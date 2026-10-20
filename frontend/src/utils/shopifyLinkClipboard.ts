/** Copy a short-lived Shopify user-link code without persisting or logging it. */
export async function copyShopifyLinkCode(
  code: string,
  clipboard: Pick<Clipboard, "writeText"> | undefined,
): Promise<boolean> {
  if (!code || typeof clipboard?.writeText !== "function") return false;
  try {
    await clipboard.writeText(code);
    return true;
  } catch {
    // Clipboard permission or browser support can fail. Allow manual selection.
    return false;
  }
}
