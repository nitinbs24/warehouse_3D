/**
 * Turns a stream of "these locations changed" bus messages into orderly refetches.
 *
 * - Collects ids until start() (the scene isn't loaded yet), so nothing is missed meanwhile.
 * - Throttles: at most one fetch per ``delay`` ms, however steady the stream (a restarting
 *   debounce would never fire in a busy warehouse).
 * - One fetch at a time, so an older reply can never overwrite a newer one.
 * - A failed fetch puts its ids back and retries after ``retryDelay`` ms.
 */
export class UpdateQueue {
    /**
     * @param {{delay: number, retryDelay: number,
     *          fetch: (ids: number[]) => Promise<any>,
     *          apply: (ids: number[], result: any) => void}} options
     */
    constructor({ delay, retryDelay, fetch, apply }) {
        Object.assign(this, { delay, retryDelay, fetch, apply });
        this.pending = new Set();
        this.started = false;
        this.running = false;
        this.timer = null;
    }

    push(ids) {
        ids.forEach((id) => this.pending.add(id));
        this.schedule(this.delay);
    }

    start() {
        this.started = true;
        this.schedule(this.delay);
    }

    stop() {
        this.started = false;
        clearTimeout(this.timer);
        this.timer = null;
        this.pending.clear();
    }

    schedule(wait) {
        // An armed timer is left alone: that's what makes it a throttle.
        if (this.started && !this.running && !this.timer && this.pending.size) {
            this.timer = setTimeout(() => {
                this.timer = null;
                this.flush();
            }, wait);
        }
    }

    async flush() {
        const ids = [...this.pending];
        this.pending.clear();
        this.running = true;
        let wait = this.delay;
        try {
            const result = await this.fetch(ids);
            if (this.started) {
                this.apply(ids, result);
            }
        } catch {
            ids.forEach((id) => this.pending.add(id));
            wait = this.retryDelay;
        } finally {
            this.running = false;
        }
        this.schedule(wait);
    }
}
