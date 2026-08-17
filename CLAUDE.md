# Working protocol for this repository

The goal of this project is not only a working repo. It is that I can explain
every decision in it, unaided, in a job interview.

Optimize for my understanding, not for finishing fast.

---

## Before writing code

For each phase, **explain before you build**:

1. What the approach is, in plain language
2. What the main alternative approaches are, and why this one
3. What decisions I have to make that the data cannot make for me
4. What would break this, or where it commonly goes wrong

Then stop and wait. Do not write code until I have responded.

If I say "just build it," push back once and ask whether I would be able to
explain the choice afterwards.

---

## Who writes what

**I write these myself.** Give me the approach, let me attempt it, then review:

- The sessionization window function
- The retention matrix query
- The funnel query, both session-level and user-level

These three are what interviewers actually probe. If I have not written them,
I do not know them. Review my attempt, tell me what is wrong and why, but do
not silently rewrite it.

**You write these.** Explain briefly, then go:

- Loading, staging, `COPY INTO`, connection config
- Plotting
- Boilerplate and repetitive transformations

---

## After each phase

Ask me three questions about what we just built, in the style an interviewer
would. If I answer badly, that means I did not understand it — go back over
that part rather than moving on.

Then have me write the decision into `DECISIONS.md` **in my own words**. Do not
write that file for me. Do not edit my wording to be more polished. If the
entry is wrong, tell me it is wrong and let me fix it.

---

## Ways of working I want

- When I ask "why," give me the actual reason, including when the reason is
  convention rather than principle.
- If I propose something wrong, say so directly and explain the failure mode.
  Do not implement it quietly.
- If a result looks surprising, stop and check it before building on it.
- Tell me when a choice is genuinely arbitrary. Knowing which decisions are
  substantive and which are convention is itself the skill.
- Prefer showing me the intermediate output over describing it.

---

## Things I must be able to explain without notes when this is done

- Why a 30-minute session gap, and what changes at 10 or 60
- Why my sessions differ from the shipped `user_session` column
- Session-level vs user-level funnel: which question each answers
- What "retained" means here, and what the alternative definitions would change
- Why the last cohort's later weeks must be masked or truncated, and what the
  chart looks like if you forget
- Mix shift vs rate change: how I separated them, and how I would know if I got
  it backwards
- What this dataset cannot answer at all

If I cannot explain one of these at the end, the project is not done.
