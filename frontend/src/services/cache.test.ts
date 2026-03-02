import { describe, it, expect, vi, beforeEach } from 'vitest';
import { requestCache } from './cache';

describe('RequestCache', () => {
  beforeEach(() => {
    // Clear the internal store between tests by invalidating everything
    requestCache.invalidate('');
  });

  it('returns fetched data on cache miss', async () => {
    const fetcher = vi.fn().mockResolvedValue({ items: [1, 2, 3] });

    const result = await requestCache.get('/test', fetcher, 30_000);

    expect(result).toEqual({ items: [1, 2, 3] });
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('returns cached data on cache hit without calling fetcher', async () => {
    const fetcher = vi.fn().mockResolvedValue({ data: 'fresh' });

    await requestCache.get('/hit-test', fetcher, 30_000);
    const result = await requestCache.get('/hit-test', fetcher, 30_000);

    expect(result).toEqual({ data: 'fresh' });
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('deduplicates concurrent requests for the same key', async () => {
    let resolvePromise: (v: unknown) => void;
    const slowFetcher = vi.fn().mockReturnValue(
      new Promise((resolve) => { resolvePromise = resolve; }),
    );

    const p1 = requestCache.get('/dedup', slowFetcher, 30_000);
    const p2 = requestCache.get('/dedup', slowFetcher, 30_000);

    resolvePromise!({ ok: true });

    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1).toEqual({ ok: true });
    expect(r2).toEqual({ ok: true });
    expect(slowFetcher).toHaveBeenCalledOnce();
  });

  it('returns stale data and revalidates in background', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce({ version: 1 })
      .mockResolvedValueOnce({ version: 2 });

    // Populate cache
    await requestCache.get('/stale', fetcher, 30_000);

    // Expire the entry by setting TTL to 0
    const result = await requestCache.get('/stale', fetcher, 0);

    // Should return stale data immediately
    expect(result).toEqual({ version: 1 });
    // Background revalidation should have been triggered
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('invalidates entries matching prefix', async () => {
    const fetcher1 = vi.fn().mockResolvedValue({ a: 1 });
    const fetcher2 = vi.fn().mockResolvedValue({ b: 2 });

    await requestCache.get('/api/missions', fetcher1, 30_000);
    await requestCache.get('/api/dashboard', fetcher2, 30_000);

    requestCache.invalidate('/api/missions');

    const newFetcher = vi.fn().mockResolvedValue({ a: 99 });
    const result = await requestCache.get('/api/missions', newFetcher, 30_000);

    expect(result).toEqual({ a: 99 });
    expect(newFetcher).toHaveBeenCalledOnce();
  });

  it('clears failed in-flight promise so next call retries', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce({ recovered: true });

    await expect(requestCache.get('/fail', fetcher, 30_000)).rejects.toThrow('network error');

    const result = await requestCache.get('/fail', fetcher, 30_000);
    expect(result).toEqual({ recovered: true });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('clear() empties the entire cache', async () => {
    const fetcher = vi.fn().mockResolvedValue({ data: 'cached' });

    await requestCache.get('/clear-test', fetcher, 30_000);
    requestCache.clear();

    const newFetcher = vi.fn().mockResolvedValue({ data: 'fresh' });
    const result = await requestCache.get('/clear-test', newFetcher, 30_000);

    expect(result).toEqual({ data: 'fresh' });
    expect(newFetcher).toHaveBeenCalledOnce();
  });

  it('evicts oldest entries when cache exceeds MAX_CACHE_SIZE', async () => {
    // Fill cache beyond the 100-entry limit
    for (let i = 0; i < 105; i++) {
      const fetcher = vi.fn().mockResolvedValue({ i });
      await requestCache.get(`/lru/${i}`, fetcher, 30_000);
    }

    // Oldest entries (0-4) should have been evicted
    const refetcher = vi.fn().mockResolvedValue({ refetched: true });
    await requestCache.get('/lru/0', refetcher, 30_000);
    expect(refetcher).toHaveBeenCalledOnce(); // Had to re-fetch because evicted

    // Recent entry (104) should still be cached
    const cachedFetcher = vi.fn().mockResolvedValue({ cached: true });
    const result = await requestCache.get('/lru/104', cachedFetcher, 30_000);
    expect(cachedFetcher).not.toHaveBeenCalled(); // Still in cache
    expect(result).toEqual({ i: 104 });
  });

  it('concurrent stale reads trigger only one background revalidation', async () => {
    let resolveReval: (v: unknown) => void;
    const initialFetcher = vi.fn().mockResolvedValue({ version: 1 });
    const revalFetcher = vi.fn().mockImplementation(
      () => new Promise((resolve) => { resolveReval = resolve; }),
    );

    // Populate cache
    await requestCache.get('/stale-dedup', initialFetcher, 30_000);

    // Two concurrent stale reads (TTL=0 forces stale)
    const r1 = await requestCache.get('/stale-dedup', revalFetcher, 0);
    const r2 = await requestCache.get('/stale-dedup', revalFetcher, 0);

    // Both return stale data immediately
    expect(r1).toEqual({ version: 1 });
    expect(r2).toEqual({ version: 1 });

    // Only one background fetch should have been triggered
    expect(revalFetcher).toHaveBeenCalledTimes(1);

    // Resolve the background revalidation
    resolveReval!({ version: 2 });
    await new Promise((r) => setTimeout(r, 10));
  });
});
