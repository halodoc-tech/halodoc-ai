# Sourcemaps

## Contents
- [When to use sourcemaps](#when-to-use-sourcemaps)
- [Where your sourcemaps live](#where-your-sourcemaps-live)
- [Expected deobfuscation workflow](#expected-deobfuscation-workflow)
- [Example S3 fetch sketch](#example-s3-fetch-sketch)
- [Example Node resolution sketch](#example-node-resolution-sketch)
- [Access expectation](#access-expectation)
- [Practical rule](#practical-rule)
- [Source confidence explanation](#source-confidence-explanation)

Use this reference when Dynatrace stack traces point to minified production bundles such as:

- `https://<your-domain>/resources/chunk-*.js`
- `https://<your-domain>/resources/polyfills-*.js`
- `https://<your-domain>/resources/main-*.js`

(Adjust the path pattern to match your own build output — this is the
Angular/webpack-style `resources/<name>-<hash>.js` convention; a different
bundler will produce a different pattern.)

## When to use sourcemaps

Use sourcemap lookup when:
- stack frames are minified and source confidence is still low
- a chunk name alone is not enough to map back to source
- you need to confirm the real file/function before patching

Prefer normal source-location signals first:
1. function name from stack trace
2. top-page to module match
3. property/method name
4. sibling pattern match

If those are insufficient, use production sourcemaps.

## Where your sourcemaps live

**Configure this for your project** — sourcemaps are typically deployed
alongside each production build to whichever storage your deploy pipeline
uses. Common patterns:

```text
s3://<your-sourcemap-bucket>/resources/<chunk-name>.js.map
```

Example:
- `chunk-SXNJTSUW.js` -> `s3://<your-sourcemap-bucket>/resources/chunk-SXNJTSUW.js.map`

If your maps are hosted elsewhere (a CDN, a private artifact store, or
uploaded directly to Dynatrace's sourcemap API), adjust the fetch step below
accordingly — the workflow (steps 1–8) is the same regardless of storage.

## Expected deobfuscation workflow

1. Extract the JS filename from the stack frame URL.
2. Resolve the corresponding `.map` object key in your sourcemap storage.
3. Fetch the sourcemap.
4. Cluster duplicate or repeated frames so the same minified location is not overcounted as multiple signals.
5. Prioritize frames that are most actionable:
   - first app-owned frame over framework/vendor frame
   - frame with a meaningful property/method name over anonymous wrapper
   - frame aligned with affected page/module over unrelated cross-cutting utility
6. Resolve the prioritized line/column back to original source.
7. Explain why the chosen resolved frame is the best source candidate.
8. Use that result as one of the source-confidence signals, not as the only signal when avoidable.

## Example S3 fetch sketch

```python
import boto3

s3 = boto3.client("s3")
bucket = "<your-sourcemap-bucket>"

def fetch_sourcemap(js_filename: str):
    map_key = f"resources/{js_filename}.map"
    return s3.get_object(Bucket=bucket, Key=map_key)["Body"].read()
```

## Example Node resolution sketch

```js
const { SourceMapConsumer } = require("source-map");

async function resolveFrame(sourcemapJson, line, column) {
  return SourceMapConsumer.with(sourcemapJson, null, (consumer) =>
    consumer.originalPositionFor({ line, column }),
  );
}
```

## Access expectation

Whatever storage holds your production sourcemaps, confirm you have read
access (IAM role, service account, or API token) before relying on this step.

If sourcemap access is unavailable:
- say that explicitly
- fall back to module/page/property-based mapping
- if confidence remains low, stop short of pretending the source is confirmed

## Practical rule

Do not edit based only on a minified vendor frame when the sourcemap is the missing link.

Use sourcemaps to raise confidence, not to skip architectural diagnosis.

## Source confidence explanation

When sourcemaps are used, explicitly record:
- which frame was selected
- why duplicate/repeated frames were deprioritized
- whether the resolved source aligns with page/module/property evidence
- whether confidence is now high, medium, or still low
