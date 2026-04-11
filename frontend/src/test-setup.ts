import '@testing-library/jest-dom/vitest';

// jsdom may disable localStorage when --localstorage-file is not set.
// Provide a simple in-memory shim so components that use localStorage don't throw.
const _storage: Record<string, string> = {};
const localStorageMock: Storage = {
  getItem: (key: string) => _storage[key] ?? null,
  setItem: (key: string, value: string) => { _storage[key] = String(value); },
  removeItem: (key: string) => { delete _storage[key]; },
  clear: () => { Object.keys(_storage).forEach(k => delete _storage[k]); },
  get length() { return Object.keys(_storage).length; },
  key: (index: number) => Object.keys(_storage)[index] ?? null,
};

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
    writable: true,
  });
}
