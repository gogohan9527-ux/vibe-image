// Wraps Web Crypto's RSA-OAEP encryption against the backend's ephemeral
// public key. Plaintext credentials never leave memory unencrypted on the
// wire — they're encrypted just-in-time before each task submission.

import { getPublicKey } from '@/api/client';

let cachedKey: CryptoKey | null = null;
let cachedPem: string | null = null;

function pemToArrayBuffer(pem: string): ArrayBuffer {
  const stripped = pem
    .replace(/-----BEGIN [^-]+-----/, '')
    .replace(/-----END [^-]+-----/, '')
    .replace(/\s+/g, '');
  const binary = atob(stripped);
  const buf = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i += 1) view[i] = binary.charCodeAt(i);
  return buf;
}

function bufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

async function loadPublicKey(): Promise<CryptoKey> {
  const { public_key_pem } = await getPublicKey();
  if (cachedKey && cachedPem === public_key_pem) return cachedKey;
  const spki = pemToArrayBuffer(public_key_pem);
  cachedKey = await crypto.subtle.importKey(
    'spki',
    spki,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  );
  cachedPem = public_key_pem;
  return cachedKey;
}

export async function encryptApiKey(plaintext: string): Promise<string> {
  const key = await loadPublicKey();
  const data = new TextEncoder().encode(plaintext);
  const ct = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, data);
  return bufferToBase64(ct);
}

export function resetPublicKeyCache(): void {
  cachedKey = null;
  cachedPem = null;
}
