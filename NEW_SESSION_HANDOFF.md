# LisaWorkout App - New Session Handoff

## Project Context

I'm building a mobile-friendly workout tracking app for my wife, hosted on Vercel. The comprehensive implementation plan is already created in `WORKOUT_APP_PLAN.md`.

**GitHub Repository:** https://github.com/matthiaskoster/LisaWorkout (private repo)

---

## Project Requirements Summary

### Core Features
- **Cardio Exercise Tracking:** AirDyne, Running (track: minutes, calories, distance)
- **Strength Exercise Tracking:** Kettlebell Swings, etc. (track: weight, reps, sets, estimated calories)
- **Day-Based Workout Planning:** Pre-configured workouts for each day (Monday-Sunday)
- **Progress Visualization:** Charts and progress bars
- **Data Persistence:** Google Sheets, Notion, or similar cloud storage

### Design Requirements
- Mobile-friendly and responsive
- Female-friendly color scheme (soft corals, lavenders, mint green)
- Clear charts and progress bars
- Touch-friendly interface

---

## Decisions Made

### User Management
- **Single user for now**, but designed for easy expansion to 2 users in the future

### Units
- **Imperial system:**
  - Weight: Pounds (lbs)
  - Distance: Miles
  - Energy: Calories

### Workout Creation
- **Both predefined AND custom workouts**
- Users can create their own workout plans
- Users can also use pre-configured workout templates

### Smart Exercise Library
- **Prevent duplicates:** Once an exercise is logged, it should appear in autocomplete/dropdown lists
- **Auto-populate from history:** Previously created exercises should be suggested to avoid creating multiples of the same type

---

## Tech Stack (from WORKOUT_APP_PLAN.md)

### Frontend
- **Next.js 14+** (App Router)
- **Tailwind CSS + shadcn/ui**
- **Recharts** for data visualization

### Data Storage
- **Google Sheets API** (recommended for MVP)
- Alternative: Supabase for future scaling

### Hosting
- **Vercel** (optimized for Next.js)

### Color Palette
- Primary: Soft coral/rose (#FF6B9D, #FFB4A2)
- Secondary: Lavender/purple (#B4A7D6, #D4C5F9)
- Accent: Mint green (#98D8C8)
- Neutrals: Soft grays and whites
- Success: Light teal (#6DD5B5)

---

## Exercise List

### [PASTE YOUR EXERCISE LIST HERE]

**Format requested:**
- Exercise name
- Type (cardio or strength)
- Specific fields needed for each exercise

**Example format:**
```
CARDIO:
- AirDyne (minutes, calories, distance)
- Running (minutes, calories, distance)
- [add more here]

STRENGTH:
- Kettlebell Swings (weight, reps, sets, estimated calories)
- [add more here]
```

---

## Files Already Created

1. **WORKOUT_APP_PLAN.md** - Comprehensive implementation plan including:
   - Complete tech stack recommendations
   - Database schema for Google Sheets
   - UI/UX design principles
   - 4-phase development timeline (~40-50 hours)
   - Mobile-first design guidelines
   - Calorie calculation formulas
   - Vercel deployment configuration

---

## Next Steps for New Claude Session

1. **Review** the WORKOUT_APP_PLAN.md file
2. **Review** the exercise list (pasted above)
3. **Set up** the Next.js project structure
4. **Implement** Phase 1 (MVP):
   - Next.js + Tailwind + shadcn/ui setup
   - Google Sheets API integration
   - Basic layout and navigation
   - Cardio exercise logger
   - Strength exercise logger
   - Simple dashboard
   - Deploy to Vercel

---

## What to Tell the New Claude Code Session

**Copy and paste this prompt:**

```
I'm building a workout tracking app called LisaWorkout. The comprehensive plan is in WORKOUT_APP_PLAN.md and the project handoff details are in NEW_SESSION_HANDOFF.md.

Please:
1. Read both files to understand the project
2. Verify you have access to the GitHub repo: https://github.com/matthiaskoster/LisaWorkout
3. Start implementing Phase 1 (MVP) as outlined in the plan
4. Use the exercise list I've provided in NEW_SESSION_HANDOFF.md
5. Commit and push progress regularly to the branch: claude/workout-app-planning-53cCA

Key requirements:
- Imperial units (lbs, miles, calories)
- Mobile-friendly with female-friendly colors
- Smart exercise library that prevents duplicates
- Both predefined and custom workout creation
- Google Sheets for data storage
```

---

## Important Notes

- The workout app plan has already been committed locally on branch `claude/workout-app-planning-53cCA`
- The new session should be able to push to the LisaWorkout repo
- Reference the existing plan rather than recreating it
- Focus on implementation starting with Phase 1

---

## Branch Information

**Working Branch:** `claude/workout-app-planning-53cCA`

This branch should be used for all development work.

---

*This handoff document contains all context needed to continue the LisaWorkout app development in a new Claude Code session.*
