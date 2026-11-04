# Integrity: what the hash chain proves, and what it does not

## 1. The two files

```
ledger/
├─ ledger.jsonl    one canonical JSON object per entry; append-only, never rewritten
├─ events.jsonl    every action, each carrying the digest of the previous one
└─ .lock           advisory lock used while writing
```

- **Canonical JSON**: `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`,
  encoded as UTF-8. The same object always produces the same bytes, on any platform, so a digest is
  a property of the content and not of the file's whitespace or key order.
- **`ledger.jsonl`** holds the entry as declared. Nothing in the tool rewrites it.
- **`events.jsonl`** is the state machine: `init`, `create`, `open`, `resolve`, `void`. Replaying it
  produces the current status of every entry.

## 2. The chain

```
genesis  = "0" * 64
hash(i)  = "sha256:" + sha256(canonical(event_i without its "hash" field))
event_1.prev_hash = genesis
event_i.prev_hash = event_{i-1}.hash
```

A `create` event carries the entry snapshot and `entry_hash = sha256(canonical(entry))`. That is
what links the two files: the snapshot must equal the line in `ledger.jsonl`, and the hash must
match its canonical form.

## 3. What each command checks

`jl verify` (exit `2` on any finding):

| Check | Failure means |
|---|---|
| `seq` is `1..N` in order | an event was inserted or removed |
| `prev_hash` matches the previous event | an event was removed or reordered |
| recomputed `hash` matches the stored one | the event was edited |
| one `create` per entry | duplicated or forged creation |
| every `create` has a line in `ledger.jsonl` | the entry file was edited or truncated |
| the snapshot equals the current entry | the entry was altered after creation |
| `entry_hash` matches the entry | same, detected through the digest |

`jl validate` adds the domain rules: id format, non-empty question, criterion with at least 10
non-space characters, `due` after `created_at` (no backdating), probabilities inside `[0,1]`, valid
interval, `void` with a reason, resolution with outcome `0|1` plus citation and locator. It also
emits two warnings that are not errors: open entries past their due date, and entries without an
origin tag.

## 4. Threat model — read this before trusting the word "integrity"

The chain detects **accidental and opportunistic edits**: a changed line, a deleted event, a
criterion quietly reworded in a text editor, a synchronisation tool merging the wrong version. That
is the realistic threat for a personal ledger, and it is cheap to check.

It does **not** stop an adversary who has write access to the whole directory: they can edit an
entry, then recompute every hash after it, and the chain will be internally consistent. Nothing here
is a signature. If you need that property:

- keep the ledger in git and push (the history is a second, off-machine witness);
- sign your commits (SSH or GPG) so the push itself is attributable;
- or record the directory digest somewhere else — `jl report` prints the digest of the report, and
  `sha256sum ledger.jsonl events.jsonl` is a one-line external anchor.

Cryptographic signing of entries is deliberately out of scope for v0.1; the README says so, and
`SECURITY.md` repeats it.

## 5. Checking by hand

```console
$ python - <<'PY'
import json, hashlib
line = open("ledger/events.jsonl", encoding="utf-8").readline()
event = json.loads(line)
stored = event.pop("hash")
canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
print(stored, "sha256:" + hashlib.sha256(canonical).hexdigest())
PY
```

Both digests must be identical. Repeat by chaining `prev_hash` if you want the whole file; that is
what `jl verify` automates.

## 6. Working with git

Appending is friendly to version control: two people adding entries produce conflicts only at the
end of the file, and keeping both blocks preserves both entries.

What is **not** supported is merging two divergent chains. Each `events.jsonl` is a single linear
history; two branches that both appended produce two chains whose `prev_hash` sequences cannot
both be true. Pick one as canonical and re-add the other's pending entries; do not hand-merge the
event files. In practice the `.lock` and the single-writer habit make this a non-issue, and it is
why the tool has no collaborative mode.

## 7. Backups

The ledger is two text files. Copy them, or commit them. There is no state anywhere else — which is
also why losing `events.jsonl` loses the status of every entry even though `ledger.jsonl` survives.
Back up both, or neither is useful.
