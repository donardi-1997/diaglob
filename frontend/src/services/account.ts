import axios from "axios";
import { getAccessToken } from "./authStorage";

const API_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

function authHeaders() {
  const token = getAccessToken();
  return token
    ? { Authorization: `Bearer ${token}` }
    : {};
}

export async function closeAccount(): Promise<void> {
  await axios.delete(`${API_URL}/api/account`, {
    headers: authHeaders(),
  });
}
