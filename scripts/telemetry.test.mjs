import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { sentryPrivacyOptions } from "../packages/ui/src/lib/telemetry.ts";

for (const app of ["teacher", "admin"]) {
  test(`${app}: SDK keeps automatic data collection off and still reports errors`, async () => {
    const require = createRequire(new URL(`../apps/${app}/package.json`, import.meta.url));
    const { BrowserClient } = require("@sentry/react");
    const envelopes = [];
    const client = new BrowserClient({
      ...sentryPrivacyOptions(),
      dsn: "https://public@telemetry.invalid/1",
      integrations: [],
      stackParser: () => [],
      transport: () => ({
        send: async (envelope) => {
          envelopes.push(envelope);
          return { statusCode: 200 };
        },
        flush: async () => true,
      }),
    });
    try {
      // Check the SDK's resolved settings, including defaults added by future upgrades.
      const collection = client.getDataCollectionOptions();
      const assertDisabled = (value) => {
        if (Array.isArray(value)) assert.deepEqual(value, []);
        else if (value && typeof value === "object") Object.values(value).forEach(assertDisabled);
        else assert.ok(value === false || value === 0, `Unexpected collection setting: ${value}`);
      };
      Object.values(collection).forEach(assertDisabled);

      client.captureEvent({ message: "Synthetic error smoke test" });
      assert.equal(await client.flush(1000), true);
      const events = envelopes
        .flatMap(([, items]) => items)
        .filter(([header]) => header.type === "event");
      assert.equal(events.length, 1);
      assert.equal(events[0][1].message, "Synthetic error smoke test");
    } finally {
      await client.close();
    }
  });
}
