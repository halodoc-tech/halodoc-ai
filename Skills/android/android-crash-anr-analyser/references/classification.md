# Issue classification and origin (Steps 4c, 4i)

## Why this file exists

`../SKILL.md` Step 4c names the classes; this table holds the trigger patterns that identify
each one and the root-cause fix that usually applies, so the class actually steers the fix
rather than being a label. Classify when it helps choose the fix; omit the classification
row from the document when it adds nothing.

| ID | Class | Trigger pattern | Typical root-cause fix |
|----|-------|-----------------|------------------------|
| C1 | Uninitialised property | `UninitializedPropertyAccessException`, `lateinit … has not been initialized` | Fix init order or DI wiring; make it constructor-injected or `lazy` |
| C2 | Missing native library | `UnsatisfiedLinkError`, `dlopen failed` | Correct ABI packaging, load ordering, or a version gate |
| C3 | Class not found / DEX | `ClassNotFoundException`, `NoClassDefFoundError` | Fix the dependency, keep rule, or multidex config |
| C4 | Null dereference | `NullPointerException`, `!!` on null | Fix the producer that emits null, or model absence in the type |
| C5 | OS / system failure | `DeadSystemException`, `TransactionTooLargeException`, `TooManyRequestsException` | Reduce payload, retry with backoff, or bound the call rate |
| C6 | ANR | Main thread unresponsive | Move or remove the blocking work (see sub-types) |
| C7 | Resource not found | `Resources$NotFoundException` | Ship the resource for every config/qualifier that needs it |
| C8 | Lifecycle violation | View touched after `onDestroyView`, `IllegalStateException` after `onSaveInstanceState` | Scope work to the correct lifecycle owner |
| C9 | Concurrency / state | `ConcurrentModificationException`, races on shared state | Confine state to one thread, snapshot, or use `StateFlow` |
| C10 | Other | Fits none of the above | Describe the specific mechanism |

**ANRs are always C6**, with a sub-type:

| Sub-type | Main thread is… | Typical fix |
|---|---|---|
| `C6-IO` | doing disk, database, or network I/O | Move to `Dispatchers.IO`; precompute or cache |
| `C6-LOCK` | waiting on a lock held by another thread, or deadlocked | Shorten the critical section, never hold a lock across I/O, remove the main thread from the lock's users |
| `C6-BINDER` | waiting on a slow IPC / system-service call | Move off main; cache the result; avoid the call on the hot path |
| `C6-HEAVY` | doing CPU-intensive work (parsing, inflation, image work, large loops) | Move to `Dispatchers.Default`; make lazy or incremental |

## Origin (Step 4i)

| Origin | Meaning | Signal |
|---|---|---|
| **APP** | A first-party frame is at or above the root frame | any `{FIRST_PARTY_PACKAGE_PREFIXES}` frame in the causal chain, even when the throw is inside a library |
| **SDK** | The deepest causal frames are a third-party library with no first-party frame above them | e.g. `okhttp3.`, `retrofit2.`, `com.google.`, `io.reactivex.` |
| **OTHER** | Only OS/framework frames | `android.`, `androidx.` internals, `java.`, `dalvik.`, `com.android.`, native |

What each origin means for the run (full flow, call-site fix only, or analysis only) is
decided in `../SKILL.md` Step 4i.
