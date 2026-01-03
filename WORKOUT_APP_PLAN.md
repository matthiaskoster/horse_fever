# Workout App - Comprehensive Implementation Plan

## Project Overview
A mobile-friendly, Vercel-hosted workout tracking application with female-friendly color scheme, designed to track various exercises and workouts with data persistence to cloud storage.

---

## Core Features

### 1. Exercise Tracking Categories

#### Cardio Exercises
- **AirDyne**
  - Minutes
  - Calories burned
  - Distance
- **Running**
  - Minutes
  - Calories burned
  - Distance

#### Strength Workouts
- **Kettlebell Swings** (and other exercises)
  - Weight
  - Reps
  - Sets
  - Estimated calories burned

### 2. Day-Based Workout Planning
- Pre-configured workouts per day (Monday, Tuesday, etc.)
- Ability to view and complete daily workout routines
- Track completion status

### 3. Progress Visualization
- Clear charts showing progress over time
- Progress bars for daily/weekly goals
- Visual feedback on workout completion

### 4. Data Persistence
- Cloud-based storage (Google Sheets, Notion, or similar)
- Real-time sync
- Historical data retention

---

## Recommended Tech Stack

### Frontend
**Next.js 14+ (App Router)**
- ✅ Vercel-optimized (native support)
- ✅ React-based for component architecture
- ✅ Built-in API routes for backend logic
- ✅ Server-side rendering for fast initial loads
- ✅ Mobile-responsive by default

### Styling
**Tailwind CSS + shadcn/ui**
- ✅ Rapid development
- ✅ Mobile-first approach
- ✅ Easy theming for female-friendly colors
- ✅ Pre-built accessible components

**Color Palette Suggestion (Female-Friendly)**
- Primary: Soft coral/rose (#FF6B9D, #FFB4A2)
- Secondary: Lavender/purple (#B4A7D6, #D4C5F9)
- Accent: Mint green (#98D8C8)
- Neutrals: Soft grays and whites
- Success: Light teal (#6DD5B5)

### Charts & Visualizations
**Recharts**
- ✅ React-based charting library
- ✅ Responsive and mobile-friendly
- ✅ Beautiful default styling
- ✅ Easy to customize

### Data Storage Options

#### Option 1: Google Sheets API (Recommended for Simplicity)
**Pros:**
- Free tier generous
- Easy to view/edit data manually
- Simple API integration
- Your wife can access raw data directly

**Cons:**
- Rate limits (read: 100 requests/100 seconds per user)
- Not ideal for real-time high-frequency updates

**Implementation:**
- Use `googleapis` npm package
- Service account authentication
- Separate sheets for: exercises, workouts, daily_plans, progress_history

#### Option 2: Notion API
**Pros:**
- Beautiful interface for manual data management
- Rich data types
- Good for planning and notes

**Cons:**
- More complex API
- Slower response times
- Rate limits (3 requests/second)

#### Option 3: Supabase (Postgres + Real-time)
**Pros:**
- Real database with relationships
- Real-time subscriptions
- Built-in auth
- Generous free tier

**Cons:**
- More setup required
- Can't easily edit data in spreadsheet format

**Recommendation:** Start with Google Sheets for MVP, migrate to Supabase if needed later.

### Authentication
**NextAuth.js (Auth.js)**
- Simple email/password auth
- Optional Google OAuth
- Session management

---

## Database Schema (Google Sheets Structure)

### Sheet 1: `exercises_cardio`
| id | date | exercise_type | minutes | calories | distance | user_id | notes |
|----|------|---------------|---------|----------|----------|---------|-------|

### Sheet 2: `exercises_strength`
| id | date | exercise_name | weight | reps | sets | calories_est | user_id | notes |
|----|------|---------------|--------|------|------|--------------|---------|-------|

### Sheet 3: `daily_workout_plans`
| id | day_of_week | workout_name | exercises_json | user_id |
|----|-------------|--------------|----------------|---------|

### Sheet 4: `workout_history`
| id | date | workout_plan_id | completed | duration_minutes | user_id |
|----|------|-----------------|-----------|------------------|---------|

---

## Application Structure

```
workout-app/
├── app/
│   ├── layout.tsx                 # Root layout with theme
│   ├── page.tsx                   # Home/dashboard
│   ├── log-workout/
│   │   └── page.tsx              # Log new workout
│   ├── cardio/
│   │   └── page.tsx              # Cardio exercise logging
│   ├── strength/
│   │   └── page.tsx              # Strength exercise logging
│   ├── schedule/
│   │   └── page.tsx              # Weekly schedule view
│   ├── progress/
│   │   └── page.tsx              # Charts and progress
│   └── api/
│       ├── exercises/
│       │   ├── cardio/route.ts
│       │   └── strength/route.ts
│       ├── workouts/route.ts
│       └── schedule/route.ts
├── components/
│   ├── ui/                        # shadcn components
│   ├── charts/
│   │   ├── ProgressChart.tsx
│   │   ├── CalorieChart.tsx
│   │   └── WeeklyProgress.tsx
│   ├── forms/
│   │   ├── CardioForm.tsx
│   │   ├── StrengthForm.tsx
│   │   └── WorkoutSelector.tsx
│   └── layout/
│       ├── Header.tsx
│       ├── Navigation.tsx
│       └── DaySelector.tsx
├── lib/
│   ├── google-sheets.ts           # Google Sheets API wrapper
│   ├── calculations.ts            # Calorie estimation formulas
│   └── utils.ts
├── types/
│   └── index.ts                   # TypeScript definitions
└── public/
    └── icons/
```

---

## Key Features Breakdown

### 1. Dashboard (Home Page)
- Today's workout overview
- Quick stats (workouts this week, calories burned)
- Progress bars (weekly goal completion)
- Quick action buttons (Log Cardio, Log Strength, View Schedule)

### 2. Cardio Exercise Logger
- Exercise type selector (AirDyne, Running)
- Input fields:
  - Minutes (number input)
  - Calories (auto-calculated or manual)
  - Distance (optional, miles/km toggle)
- Date picker (defaults to today)
- Submit button with loading state

### 3. Strength Exercise Logger
- Exercise name (dropdown + custom input)
- Input fields:
  - Weight (lbs/kg toggle)
  - Reps
  - Sets
  - Estimated calories (auto-calculated)
- Date picker
- "Add Another Set" button
- Submit button

### 4. Weekly Schedule
- 7-day view (Monday-Sunday)
- Each day shows:
  - Planned workout name
  - Exercise list
  - Completion checkbox
  - Edit button
- "Start Today's Workout" button

### 5. Progress Page
Charts to include:
- **Weekly Calories Burned** (bar chart)
- **Workout Frequency** (line chart over time)
- **Exercise Type Distribution** (pie chart)
- **Monthly Progress** (comparison chart)
- **Personal Records** (list view)

### 6. Settings
- User profile
- Units preference (imperial/metric)
- Calorie calculation preferences
- Color theme customization
- Data export option

---

## Calorie Calculation Formulas

### Cardio Estimates
**Running:**
- Calories = (MET value × weight in kg × time in hours)
- MET for running: ~10 (moderate pace)

**AirDyne:**
- Calories = ~10-15 per minute (based on intensity)

### Strength Training
**General formula:**
- Calories per set = (weight × reps × 0.01) + (MET × weight in kg × time in minutes / 60)
- MET for resistance training: ~6

---

## Implementation Phases

### Phase 1: MVP (Week 1-2)
- [ ] Set up Next.js project with Tailwind CSS
- [ ] Install and configure shadcn/ui
- [ ] Implement Google Sheets API integration
- [ ] Create basic layout and navigation
- [ ] Build cardio exercise logger
- [ ] Build strength exercise logger
- [ ] Create simple dashboard
- [ ] Deploy to Vercel

### Phase 2: Scheduling & Planning (Week 2-3)
- [ ] Implement weekly schedule view
- [ ] Create workout plan builder
- [ ] Add day-based workout assignments
- [ ] Implement workout completion tracking
- [ ] Add "Start Workout" flow

### Phase 3: Progress & Visualization (Week 3-4)
- [ ] Integrate Recharts
- [ ] Build weekly calorie chart
- [ ] Build workout frequency chart
- [ ] Add progress bars to dashboard
- [ ] Create historical data views

### Phase 4: Polish & Enhancement (Week 4+)
- [ ] Add authentication
- [ ] Implement settings page
- [ ] Add data export functionality
- [ ] Progressive Web App (PWA) features
- [ ] Offline support
- [ ] Push notifications for workout reminders

---

## Mobile-First Design Principles

1. **Touch-Friendly Targets**
   - Minimum button size: 44x44px
   - Adequate spacing between interactive elements

2. **Single-Column Layouts**
   - Stack elements vertically on mobile
   - Use grid layouts only on tablet+

3. **Bottom Navigation**
   - Fixed bottom nav for primary actions
   - Thumb-zone optimization

4. **Quick Input Methods**
   - Number pads for numeric inputs
   - Dropdowns with common values
   - "Quick Log" buttons with preset values

5. **Gesture Support**
   - Swipe to navigate days
   - Pull to refresh
   - Swipe to delete entries

---

## Vercel Deployment Configuration

```json
// vercel.json
{
  "framework": "nextjs",
  "regions": ["iad1"],
  "env": {
    "GOOGLE_SHEETS_PRIVATE_KEY": "@google-sheets-key",
    "GOOGLE_SHEETS_CLIENT_EMAIL": "@google-sheets-email",
    "SPREADSHEET_ID": "@spreadsheet-id"
  }
}
```

**Environment Variables Needed:**
- `GOOGLE_SHEETS_PRIVATE_KEY`
- `GOOGLE_SHEETS_CLIENT_EMAIL`
- `SPREADSHEET_ID`
- `NEXTAUTH_SECRET` (if using authentication)
- `NEXTAUTH_URL`

---

## Google Sheets Setup Steps

1. Create a Google Cloud Project
2. Enable Google Sheets API
3. Create a Service Account
4. Download JSON credentials
5. Create a new Google Sheet
6. Share sheet with service account email
7. Note the Spreadsheet ID from URL

---

## Potential Enhancements

### Future Features
- **Social Features**
  - Share progress with friends
  - Workout challenges

- **AI/Smart Features**
  - Workout recommendations
  - Automatic weight progression suggestions
  - Form check reminders

- **Integrations**
  - Apple Health / Google Fit
  - Fitness tracker sync (Fitbit, Garmin)

- **Advanced Analytics**
  - One-rep max tracking
  - Volume load calculations
  - Muscle group distribution

- **Gamification**
  - Achievement badges
  - Streak tracking
  - Level system

---

## Estimated Development Time

- **MVP (Basic Tracking):** 15-20 hours
- **Scheduling Features:** 8-10 hours
- **Charts & Progress:** 10-12 hours
- **Polish & PWA:** 8-10 hours

**Total:** ~40-50 hours for full-featured v1.0

---

## Next Steps

1. **Review this plan** and provide feedback
2. **Create GitHub repository** for the project
3. **Set up Google Sheets** and get API credentials
4. **Start Phase 1** implementation
5. **Iterative development** with regular feedback

---

## Questions to Consider

Before starting implementation:

1. **Authentication:** Does your wife need a login, or is this single-user?
2. **Exercise Library:** How many different exercises to support initially?
3. **Unit Preferences:** Imperial (lbs/miles) or metric (kg/km)?
4. **Workout Plans:** Should users create their own, or just use predefined ones?
5. **Data Privacy:** Will this be private or potentially shared?
6. **Budget:** Are you okay with free tier limitations, or willing to pay for services?

---

## Resources

- Next.js Docs: https://nextjs.org/docs
- shadcn/ui: https://ui.shadcn.com/
- Recharts: https://recharts.org/
- Google Sheets API: https://developers.google.com/sheets/api
- Vercel Deployment: https://vercel.com/docs

---

*This plan is flexible and can be adjusted based on your feedback and priorities.*
