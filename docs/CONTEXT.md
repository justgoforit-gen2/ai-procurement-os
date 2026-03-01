# Procurement OS — Context & Assumptions

## Status
Skeleton / stub phase. No real OCR, spend, or AP logic yet.

## Kit definitions
| Kit | Modules |
|-----|---------|
| Standard | spend |
| Expansion | spend + rfx |
| Automation | spend + rfx + ocr |
| Full Package | spend + rfx + ocr + ap |

Toggle modules in `config/app/modules.yaml`.

## Key constraints
- Sensitive content (supplier names, prices, line items, PDF text) must never
  be logged or persisted.
- Audit logs store metadata only: request_id, timestamp, SHA-256 hash, counts.
- OCR runtime behaviour is fully driven by `config/ocr/default.yaml`.

## TODO
- [ ] Implement spend classification (proc_core/spend)
- [ ] Implement RFx creation (proc_core/rfx)
- [ ] Integrate real OCR engine (tesseract / Azure DI / Google Vision)
- [ ] Implement AP invoice processing (proc_core/ap)
- [ ] Add authentication (config/app/security.yaml: auth.enabled: true)
