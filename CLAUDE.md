# Instructions for coding agents

## How to work
- Do the whole task you were asked for without stopping to ask permission for individual steps.
- Never change a file until Jay approves. Read and plan first, then show the exact diff of every change and stop. Apply it only after Jay approves in the chat.
- Never commit or push until Jay approves in the chat.
- Never deploy to live traffic or move traffic. Deploy server changes only to a no-traffic tag, and only when Jay asks.
- Run all eleven server test suites before any server commit.
- Never print secret values or push tokens. When listing settings, print names only.
- Test notifications go only to Jay's own phone.

## Reporting to Jay
- Write every reply in plain text. No tables, no diagrams, no emoji.
- Use short bullets and plain English. Say what changed and what it means, not how you worked.
- When you show a diff, show only the changed lines, with the file path and line numbers.
- End every reply with a section headed REPORT: a few short bullets Jay can copy into his planning chat, covering what you did, what changed, what is committed or deployed and what is not, and anything waiting on his decision.
