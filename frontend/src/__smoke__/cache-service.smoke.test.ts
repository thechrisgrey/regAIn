/**
 * Smoke: Cache service (RequestCache)
 *
 * Verifies the SWR cache works for basic operations:
 * - get: cache miss triggers fetcher, cache hit returns cached data
 * - invalidate: removes entries matching a prefix
 * - clear: empties the entire cache
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { requestCache } from '../services/cache';

describe('Smoke: RequestCache', () => {
  beforeEach(() => {
    requestCache.clear();
  });

  it('fetches data on cache miss', async () => {
    // First access must call the fetcher
    const fetcher = vi.fn().mockResolvedValue({ data: 'hello' });
    const result = await requestCache.get('/smoke-miss', fetcher, 30_000);

    expect(result).toEqual({ data: 'hello' });
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('returns cached data on cache hit without calling fetcher again', async () => {
    // Repeated access within TTL must not re-fetch
    const fetcher = vi.fn().mockResolvedValue({ data: 'cached' });

    await requestCache.get('/smoke-hit', fetcher, 30_000);
    const result = await requestCache.get('/smoke-hit', fetcher, 30_000);

    expect(result).toEqual({ data: 'cached' });
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('invalidate removes entries by prefix', async () => {
    // After invalidation, the next access must call the fetcher
    const fetcher = vi.fn().mockResolvedValue({ count: 1 });
    await requestCache.get('/smoke/prefix/item', fetcher, 30_000);

    requestCache.invalidate('/smoke/prefix');

    const newFetcher = vi.fn().mockResolvedValue({ count: 2 });
    const result = await requestCache.get('/smoke/prefix/item', newFetcher, 30_000);

    expect(result).toEqual({ count: 2 });
    expect(newFetcher).toHaveBeenCalledOnce();
  });

  it('clear empties the entire cache', async () => {
    // After clear, all cached entries should be gone
    const fetcher = vi.fn().mockResolvedValue({ x: 1 });
    await requestCache.get('/smoke/clear', fetcher, 30_000);

    requestCache.clear();

    const newFetcher = vi.fn().mockResolvedValue({ x: 2 });
    const result = await requestCache.get('/smoke/clear', newFetcher, 30_000);

    expect(result).toEqual({ x: 2 });
    expect(newFetcher).toHaveBeenCalledOnce();
  });

  it('deduplicates concurrent requests for the same key', async () => {
    // Two simultaneous requests for the same key should result in one fetch
    let resolve: (v: unknown) => void;
    const fetcher = vi.fn().mockReturnValue(
      new Promise((r) => { resolve = r; }),
    );

    const p1 = requestCache.get('/smoke/dedup', fetcher, 30_000);
    const p2 = requestCache.get('/smoke/dedup', fetcher, 30_000);

    resolve!({ deduped: true });

    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1).toEqual({ deduped: true });
    expect(r2).toEqual({ deduped: true });
    expect(fetcher).toHaveBeenCalledOnce();
  });
});
