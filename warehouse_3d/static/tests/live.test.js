import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, Deferred } from "@odoo/hoot-dom";
import { UpdateQueue } from "@warehouse_3d/view3d/live";

/** Let pending promise callbacks run (timers are faked by Hoot, promises are not). */
async function settle() {
    for (let i = 0; i < 10; i++) {
        await Promise.resolve();
    }
}

function makeQueue({ fetch } = {}) {
    const calls = [];
    const applied = [];
    const queue = new UpdateQueue({
        delay: 150,
        retryDelay: 5000,
        fetch: fetch || (async (ids) => {
            calls.push([...ids].sort());
            return ids;
        }),
        apply: (ids, result) => applied.push([...ids].sort()),
    });
    return { queue, calls, applied };
}

describe("UpdateQueue", () => {
    test("collects ids before start, fetches them once after start", async () => {
        const { queue, calls } = makeQueue();
        queue.push([1, 2]);
        queue.push([2, 3]);
        await advanceTime(1000);
        expect(calls).toEqual([]); // not started: the scene isn't loaded yet
        queue.start();
        await advanceTime(150);
        await settle();
        expect(calls).toEqual([[1, 2, 3]]);
    });

    test("a steady stream still refreshes every delay (throttle, not debounce)", async () => {
        const { queue, calls } = makeQueue();
        queue.start();
        for (let i = 0; i < 10; i++) {
            queue.push([i]);
            await advanceTime(100);
            await settle();
        }
        // 1 s of messages every 100 ms: a restarting 150 ms debounce would never fire.
        expect(calls.length >= 5).toBe(true, { message: `only ${calls.length} refreshes` });
    });

    test("one fetch at a time: replies are applied in request order", async () => {
        const first = new Deferred();
        const requests = [];
        const { queue, applied } = makeQueue({
            fetch: (ids) => {
                requests.push([...ids]);
                return requests.length === 1 ? first : Promise.resolve(ids);
            },
        });
        queue.start();
        queue.push([7]);
        await advanceTime(150);
        queue.push([7, 8]); // arrives while the first request is still in flight
        await advanceTime(1000);
        await settle();
        expect(requests.length).toBe(1); // no second request overtaking the first
        first.resolve([7]);
        await settle();
        await advanceTime(150);
        await settle();
        expect(requests).toEqual([[7], [7, 8]]);
        expect(applied).toEqual([[7], [7, 8]]);
    });

    test("a failed fetch keeps its ids and retries later", async () => {
        let fail = true;
        const { queue, applied } = makeQueue({
            fetch: async (ids) => {
                if (fail) {
                    fail = false;
                    throw new Error("network down");
                }
                return ids;
            },
        });
        queue.start();
        queue.push([4, 5]);
        await advanceTime(150);
        await settle();
        expect(applied).toEqual([]);
        await advanceTime(5000);
        await settle();
        expect(applied).toEqual([[4, 5]]);
    });

    test("stop drops pending work", async () => {
        const { queue, calls } = makeQueue();
        queue.start();
        queue.push([1]);
        queue.stop();
        await advanceTime(1000);
        await settle();
        expect(calls).toEqual([]);
    });
});
