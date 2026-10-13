# Limitations

## Known detection errors

| Case | What happens | Impact |
|---|---|---|
| Masked card number `VISA DEBIT 4532 **** **** 1187` | `4532` tagged as `ACCOUNT` by PII-Tracer | over-masking (restored correctly) |
| The bank's own phone number in documents | masked as `MA_PHONE` | over-masking; add it to `ALLOW_LIST` |
| Same IBAN with and without spaces | two different placeholders | the model may treat them as two accounts |
| Full name split | `Amina` and `El Idrissi` as `<PERSON_1>` and `<PERSON_2>` | the model may drop one part |
| Darija in Latin script, Arabic-script names | lower recall than French | possible leak |
| Foreign identity numbers (DNI, SSN, passports…) | masked in tracer mode only, typed `ACCOUNT` or `MA_CIN` | the model may call a foreign ID a Moroccan CIN; presidio mode does not detect them |
| Address alone (`bd Abdelmoumen`) | masked as `ADDRESS` | the model cannot reason on it (e.g. nearest branch): resolve it inside a tool, which receives the real value |

## What is not protected

ezpiizi protects what the **LLM provider** receives. Real values remain in:
- the application state and checkpoints;
- traces of non-LLM steps (agent and tool spans);
- the vault itself (in memory).

## Vault

- **In memory, per process:** lost on restart (placeholders are renumbered, which is harmless since
  stored messages hold real values) and not shared between several server processes. For production,
  back it with an encrypted store (Redis or Postgres, with a TTL).
- `VAULTS` grows with the number of conversations: purge vaults of finished conversations.

## Performance

- presidio mode: a few ms per message.
- tracer mode: 60–430 ms per **new** message on an Apple GPU (already-seen texts are cached); model load
  ~4 s, first inference ~3 s.
- All detection runs in **one thread**: throughput is about one conversation turn per second on a laptop,
  whatever the number of concurrent conversations. Scale with a GPU server and batching, or a dedicated
  PII service.

## Security

PII-Tracer is loaded with `trust_remote_code=True`. Its code was reviewed at `config.TRACER_REVISION`:
keep the revision pinned, and review the code again before changing it.
