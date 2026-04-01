---
type: email-template
date: 2026-04-04
topic: LoreConvo session memory -- companion to blog post
linked_post: blog_why_claude_sessions_start_from_zero_2026_04_01.md
status: draft
---

# Email Template: LoreConvo Session Memory

**Use case:** Newsletter or cold outreach to data engineers, analytics engineers,
and AI practitioners who use Claude for technical work.

---

**Subject:** Your Claude sessions have amnesia. Here is the fix.

**Preview text:** 440,000 tokens per month -- gone. Here is what we did about it.

---

Hi [Name],

Quick question: how many minutes did you spend this week re-explaining your project
to Claude?

Not a trick question. It happens every session. You open a new conversation and your
AI assistant knows nothing -- not what you are building, not what you decided last
Tuesday, not what failed last Thursday. You rebuild context. Then you work.

We tracked this on our own projects. Before solving it, we were burning roughly
440,000 tokens per month on context re-injection that added zero new value.

We wrote up how we solved it -- and why the common workarounds (pasting context
manually, long sessions, custom instructions) all have failure modes that show up at
exactly the wrong time.

[Read: Why Your Claude Sessions Start From Zero (And What to Do About It)]
[LINK TO BLOG POST]

The short version: LoreConvo auto-saves session context at session close and
auto-loads it at session start. Hooks that run in the background. Nothing to maintain.

If you are doing serious project work with Claude -- pipelines, consulting engagements,
agentic workflows -- it changes how the tool feels.

Free tier available. Takes about five minutes to set up.

[Get LoreConvo]
[LINK TO TOOLS PAGE]

--
Debbie
Labyrinth Analytics Consulting
labyrinthanalyticsconsulting.com

---

**Notes for Debbie:**
- Replace [LINK TO BLOG POST] with published post URL before sending
- Replace [LINK TO TOOLS PAGE] with the direct LoreConvo install link once marketplace is live
- Subject line A/B option: "440,000 tokens re-explaining your project (every month)"
- Keep the tone personal -- this reads as a note from Debbie, not a press release
- Best send day/time: Tuesday or Wednesday morning (when engineers are mid-project)
