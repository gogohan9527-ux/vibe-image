import { ref } from 'vue';

export const isDemoDenied = ref(false);

export function getDemoToken(): string {
  return localStorage.getItem('demo_token') ?? '';
}

export function saveDemoToken(token: string): void {
  localStorage.setItem('demo_token', token);
}
