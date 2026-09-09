# WORK ORDER: Redslip, steal Accord's reviewer packet

You are in `projects/vault`. The product wordmark is **Redslip**. Do not write VAULT in the UI.

Competitor: Accord (https://devpost.com/software/accord-j973qz) and CinemaOps (https://devpost.com/software/cinemaops). They give a reviewer a packet they can act on: the title, the failed spec, the measured number, what to do.

## Do this

1. Keep the rejection-ledger layout (Playfair masthead, index immediately visible). Do not restyle into a dashboard.
2. Rename any remaining on-screen VAULT copy to Redslip.
3. The expanded title panel already has findings. Add a primary control **Copy red slip** that copies a plain-text rejection slip: title, each failed check with measured vs spec, and the existing cost-to-rescue line. Use data already on the page / `/api/title/...`. No new backend.
4. No Inter. No em dash. No emoji.

## Done when

A QC lead can filter failing titles, open one, copy a red slip, and paste it into an email without leaving the page.
