# Course Notes Hub — Design (built 2026-06-11)

## Decisions (user-approved via grill session)
- Q1: Notes live in ONE database (not page tree, not hybrid).
- Q2: Note granularity = one page per textbook chapter; sessions append inside.
- Q3: Course hubs = pages in a Courses database (template-able, relation-capable).
- Q4: Lean schema (below). Remaining decisions delegated to Claude.

## Built structure (all under 🗂 Command Center V2)

### 🎓 Courses DB — db `2909831a32d743dc88d9a53f7a9112cb`, ds `4ef89411-373d-4f12-9815-9285d335e098`
Props: Course (title), Code, Instructor, Term, Canvas Link (url).
Rows (each = course hub page with cover/icon, quick-facts callout, Canvas + NotebookLM links,
inline "📝 My Notes" gallery + "📋 Assignments" table):
- ⚖️ Business Law `37c2b136-1dc0-8140-841c-de24a67e9223` (BLAW-261-353)
- 📣 Marketing `37c2b136-1dc0-8105-9a12-f4358412e040` (MKT-230-353)

### 📒 Course Notes DB — db `9ee13e9362a64bd798b8ce74b04b5cb8`, ds `eb345ba5-2277-4278-b46a-372f64cd71d6`
Props: Name, Course (relation→Courses, DUAL "Notes"), Class (select ⚖️ BLAW/📣 MKT),
Source (📖/🎓/🎥/🧪/💬), Chapter (number), Status (📥 Capturing/🔄 Reviewing/✅ Mastered),
Reviewed (date), Exam (Exam 1/2/Midterm/Final).
Views: default table; 🧠 Study Tracker (board by Status); 🎯 Exam Prep (board by Exam).
Template page `37d2b136-1dc0-81fe-b214-c0a943ee87cb`: Cornell-style — cue questions,
session-dated notes, key-terms table, self-quiz toggles, summary callout. Duplicate per chapter.

### Dashboard page `3792b136-1dc0-81e3-...`: purple 🎓 nav callout → both course pages + Notes DB.

## Constraints discovered
- View DSL cannot filter on relation properties (silently dropped) → Class select powers
  per-course view filters; relation kept for back-links/rollups.
- column/column_list blocks cannot host databases or linked views (two 400s).
- MCP update-page cannot edit non-page blocks → python notion_client appended nav callout.
- DO NOT set NOTION_COURSES_DB_ID env: exporter would write relation into Canvas_API
  "Course" select property → validation error. Assignments link to courses via select filter.

## Per-note workflow
Duplicate template → rename "Ch. # — Topic" → set Class + Chapter (+ Course relation optional)
→ notes inside. Course page gallery + boards pick it up automatically.
