# FRONTEND COMPREHENSIVE TESTING PLAN

**Frontend URL**: http://localhost:3001
**Backend URL**: http://localhost:8000
**Status**: ✅ Running (Vite dev server)

---

## TEST MATRIX

### 1. ROUTE ACCESSIBILITY (Schema & Navigation)

| Route | Expected | Purpose |
|-------|----------|---------|
| `/` | Home page with login/signup buttons | Public landing |
| `/login` | Login form (email, password, submit) | Authentication |
| `/signup` | Signup form (email, username, password, confirm) | Registration |
| `/dashboard` | User greeting, ELO, room buttons, recent sessions | Main hub |
| `/rooms/classic` | Topic selector → Questions → Session summary | Learning mode |
| `/rooms/challenge` | Rank display, rank selector, skip option | Competition mode |
| `/profile` | Concept theta bars, session history, rank badge | User stats |

### 2. BUTTON FUNCTIONALITY TESTS

#### Home Page `/`
- [ ] "Login" button → navigates to `/login`
- [ ] "Sign Up" button → navigates to `/signup`
- [ ] Logo/title clickable → returns to `/`

#### Login Page `/login`
- [ ] Email input accepts email format
- [ ] Password input hides text
- [ ] "Login" button disables during submit
- [ ] Success → redirects to `/dashboard`
- [ ] Error message shown on invalid credentials
- [ ] "Sign Up" link → navigates to `/signup`

#### Signup Page `/signup`
- [ ] Email, username, password inputs work
- [ ] Password confirm field matches
- [ ] "Sign Up" button disables during submit
- [ ] Success → redirects to `/login` or auto-login to `/dashboard`
- [ ] "Already have account?" → redirects to `/login`

#### Dashboard `/dashboard`
- [ ] "Classic Room" button → navigates to `/rooms/classic`
- [ ] "Challenge Room" button → navigates to `/rooms/challenge` (or locked if < 5 games)
- [ ] "Profile" button → navigates to `/profile`
- [ ] "Logout" button → clears token, redirects to `/`
- [ ] Session history items clickable (if implemented)

#### Classic Room `/rooms/classic`
- [ ] Topic selector (Geography, History, Mix) works
- [ ] "Start" button → submits topic, loads first question
- [ ] Question options are clickable buttons
- [ ] All 4 options present and shuffled
- [ ] "Hint" button shows hint without revealing answer
- [ ] Option buttons lock during loading
- [ ] "Next Question" button appears after answer
- [ ] Session ends after 10 questions with summary

#### Challenge Room `/rooms/challenge`
- [ ] Current rank displayed
- [ ] Rank selector shows available ranks
- [ ] "Start Match" button → loads first question
- [ ] Options based on rank (2 for Bronze, 4 for others)
- [ ] Timer visible if rank >= 3
- [ ] No hint button visible
- [ ] Match ends with win/loss result
- [ ] Rank change animation if promoted

#### Profile `/profile`
- [ ] Concept list with theta bars/charts
- [ ] Session history table with dates, scores
- [ ] Rank badge shows current rank
- [ ] Logout button present

### 3. STATS & DATA DISPLAY

#### Dashboard Stats
- [ ] ELO score displays correctly
- [ ] Current level displays (Novice/Learner/Proficient/Expert)
- [ ] Recent session count accurate
- [ ] Points/XP displays if implemented

#### Classic Room Stats
- [ ] Question counter (e.g., "3/10") increments
- [ ] Accuracy percentage updates
- [ ] Theta change shown after each answer
- [ ] Final score/accuracy in summary

#### Challenge Room Stats
- [ ] Current ELO rating displayed
- [ ] Wins/Losses ratio shown
- [ ] Skip attempts remaining visible
- [ ] Win/loss message at end

#### Profile Stats
- [ ] Concept theta values range from -3 to 3
- [ ] Response count per concept shown
- [ ] Session history sortable by date
- [ ] Level badges (Beginner, Learning, Proficient, Advanced)

### 4. LAYOUT & RESPONSIVE DESIGN

- [ ] Mobile view (320px) — stacks properly
- [ ] Tablet view (768px) — 2-column layout
- [ ] Desktop view (1024px+) — full width
- [ ] Navigation menu visible on all screen sizes
- [ ] Buttons accessible and not too small
- [ ] Forms properly formatted
- [ ] Questions readable and well-spaced

### 5. LOADING STATES

- [ ] Loading spinner shown during API calls
- [ ] Buttons disabled during submission
- [ ] Question options locked while loading
- [ ] Session loading screen between questions
- [ ] No flash of unloaded content

### 6. ERROR HANDLING

- [ ] Invalid credentials → error message
- [ ] Network error → retry option or error message
- [ ] 404 routes → redirect to home or error page
- [ ] Missing token → redirect to login
- [ ] Session expired → prompt to login again

### 7. AUTH STATE

- [ ] Logged out: `/dashboard` redirects to `/login`
- [ ] Logged in: `/login` redirects to `/dashboard`
- [ ] Token stored in localStorage (`adaptiq_token`)
- [ ] Dev mode (`?dev=true`) shows test user selector
- [ ] Dev panel allows quick login to test users

### 8. DEV MODE (`?dev=true`)

- [ ] Panel appears in bottom-right
- [ ] Shows 5 test user buttons
- [ ] Clicking user auto-logs in (calls login endpoint)
- [ ] Test users available: novice_reader, geo_expert, hist_expert, balanced, challenger
- [ ] Can switch between users without manual logout

---

## TEST EXECUTION PLAN

### Step 1: Home Page Test
```
1. Load http://localhost:3001
2. Click "Login" → lands on /login
3. Click browser back → lands on /
4. Click "Sign Up" → lands on /signup
5. Click "Sign Up" link → lands on /login
```

### Step 2: Auth Test
```
1. Click "Sign Up"
2. Fill form with test data: email, username, password
3. Submit → should redirect to /login or /dashboard
4. Login with correct credentials
5. Should land on /dashboard
6. Verify JWT token in localStorage
```

### Step 3: Dashboard Test
```
1. On /dashboard, verify:
   - Username displayed
   - ELO/Level shown
   - "Classic Room", "Challenge Room", "Profile" buttons present
   - "Logout" button present
2. Click each button → navigate to correct route
```

### Step 4: Classic Room Test
```
1. Click "Classic Room"
2. Select topic (Geography)
3. Click "Start"
4. Verify first question loads:
   - Question text visible
   - 4 shuffled options present
   - "Hint" button visible
   - Timer/progress "1/10"
5. Click "Hint" → hint displays without revealing answer
6. Click an option → locks all buttons
7. Wait for backend response
8. Show correct answer + explanation
9. Click "Next" → loads question 2
10. Repeat until question 10
11. After question 10 → "Session Summary" screen
12. Should show: score, accuracy, ELO change
13. Click "Play Again" or "Dashboard"
```

### Step 5: Challenge Room Test
```
1. Click "Challenge Room"
2. Verify current rank displayed
3. If available, see "Skip to Next Rank" option
4. Click "Start Match"
5. Verify:
   - Question text visible
   - Correct number of options (2 for Bronze, 4+)
   - Timer if rank >= 3
   - NO hint button
6. Answer 10 questions
7. See match result: Win/Loss
8. Check if rank changed (animated if promoted)
```

### Step 6: Profile Test
```
1. Click "Profile"
2. Verify sections:
   - "Concepts" with theta values/bars
   - "Recent Sessions" table
   - "Rank Badge" showing current rank
3. Check data accuracy against database
```

### Step 7: Dev Mode Test
```
1. Load http://localhost:3001?dev=true
2. Bottom-right panel should appear
3. Show 5 test users
4. Click "Novice Reader"
5. Auto-login → redirect to /dashboard
6. Logged in as novice_reader
7. Can switch to other users
8. Panel persists on all pages
```

---

## EXPECTED RESULTS

✅ **If all tests pass:**
- All routes accessible
- All buttons functional
- Stats display correctly
- Auth flow works
- Dev mode works
- Responsive layout looks good
- Loading states present
- Error handling graceful

❌ **If tests fail:**
- Document which button/route fails
- Note error message shown
- Check browser console for JS errors
- Verify backend is running (API calls)
- Check token in localStorage

---

## VERIFICATION CHECKLIST

After testing, verify:
- [ ] Can log in with test user
- [ ] Can complete Classic Room session (10 questions)
- [ ] Can view Challenge Room
- [ ] Can view Profile with theta data
- [ ] Logout clears token
- [ ] Dev mode works
- [ ] No console errors
- [ ] Pages load in < 2s
- [ ] Buttons responsibly disable during loading
- [ ] Stats match backend data

