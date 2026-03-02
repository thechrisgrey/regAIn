interface CacheEntry<T = unknown> {
  data: T;
  timestamp: number;
  promise?: Promise<T>;
}

class RequestCache {
  private store = new Map<string, CacheEntry>();

  get<T>(key: string, fetcher: () => Promise<T>, ttlMs: number): Promise<T> {
    const entry = this.store.get(key) as CacheEntry<T> | undefined;
    const now = Date.now();

    // Deduplicate initial fetch: if no cached data exists, return the in-flight promise
    if (entry?.promise && !entry.timestamp) {
      return entry.promise;
    }

    // Fresh cache hit
    if (entry && now - entry.timestamp < ttlMs) {
      return Promise.resolve(entry.data);
    }

    // Stale entry exists — return stale data, revalidate in background
    if (entry) {
      this.revalidate(key, fetcher);
      return Promise.resolve(entry.data);
    }

    // No entry — fetch and cache
    const promise = fetcher()
      .then((data) => {
        this.store.set(key, { data, timestamp: Date.now() });
        return data;
      })
      .catch((err) => {
        // Remove failed in-flight promise so next call retries
        const current = this.store.get(key);
        if (current?.promise === promise) {
          this.store.delete(key);
        }
        throw err;
      });

    this.store.set(key, { data: undefined as T, timestamp: 0, promise });
    return promise;
  }

  invalidate(keyPrefix: string): void {
    for (const key of this.store.keys()) {
      if (key.startsWith(keyPrefix)) {
        this.store.delete(key);
      }
    }
  }

  clear(): void {
    this.store.clear();
  }

  private revalidate<T>(key: string, fetcher: () => Promise<T>): void {
    const existing = this.store.get(key) as CacheEntry<T> | undefined;
    if (existing?.promise) return;

    const revalPromise = fetcher()
      .then((data) => {
        const current = this.store.get(key);
        if (current?.promise === revalPromise) {
          this.store.set(key, { data, timestamp: Date.now() });
        }
      })
      .catch(() => {
        const current = this.store.get(key);
        if (current?.promise === revalPromise) {
          this.store.set(key, { ...current, promise: undefined });
        }
      });

    this.store.set(key, { ...existing!, promise: revalPromise });
  }
}

export const requestCache = new RequestCache();
