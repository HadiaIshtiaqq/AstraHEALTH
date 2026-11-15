# ASTRAHEALTH AI — NASA Space Apps Challenge (Karachi Local Judging)
## Official 7-Slide Pitch Deck, Timing Script & Judge Q&A Defense Guide

---

### Event & Slot Details
- **Date & Time:** Sunday, 15 November 2026 | 4:00 PM – 6:00 PM PKT
- **Total Duration:** 10 Minutes Total
  - **Presentation:** 7 Minutes strict (timed)
  - **Q&A with Assigned Judge:** 3 Minutes
- **Format:** Exactly 7 Slides (including Title Slide)
- **Judging Criteria:** Impact (20%), Creativity (20%), Validity (20%), Relevance (20%), Presentation (20%)
- **Interactive Presentation Deck:** [`docs/NSAC_Karachi_Presentation_7_Slides.html`](file:///c:/Users/hadia/AstraHealth%20AI/docs/NSAC_Karachi_Presentation_7_Slides.html) (Open in Chrome/Edge, press `F` for Fullscreen, `S` for Speaker Notes, `Space`/`→` to advance, features built-in 7-minute timer).

---

## 1. Team Role Allocation (Recommendation)

For a smooth, professional 10-minute slot:
- **Primary Presenter (1 person or split between 2):** Delivers the 7-minute pitch smoothly without reading slides line-by-line. Speaks with clarity, empathy, and conviction. Keeps an eye on the timer.
- **Technical & Architecture Lead (Q&A):** Answers questions on ML models, offline air-gap security, Python/FastAPI backend, DPAPI encryption, and tests.
- **Flight & Space Domain Lead (Q&A):** Answers questions on NASA HRP hazards, NASA-STD-3001, Mars communication delay, SANS, and clinical countermeasures.
- **Timekeeper / Navigator:** Operates laptop, advances slides, and gives silent hand signals at 3 min remaining, 1 min remaining, and 30 seconds remaining.

---

## 2. Minute-by-Minute 7-Minute Slide Deck & Speaker Script

```
0:00 ─── 0:50 ─── 1:50 ─── 2:50 ─── 3:45 ─── 4:50 ─── 5:50 ─── 7:00
Slide 1   Slide 2   Slide 3   Slide 4   Slide 5   Slide 6   Slide 7
(Title)  (Problem) (Archit.)  (NASA)    (UX/Demo) (Tests)  (Impact)
```

---

### Slide 1: Title Slide — The Deep Space Reality
- **Timing:** 0:00 – 0:50 (50 seconds)
- **Primary Criteria Target:** Impact & Presentation Hook
- **Slide Visuals:**
  - Dark cosmic UI with glowing cyan accents.
  - Project Title: **ASTRAHEALTH AI**
  - Subtitle: *Autonomous Astronaut Health Intelligence for Long-Duration Missions*
  - Team Information: Team Name, Member Names & Roles.
  - Callout Banner: *"In deep space, Earth is 22 light-minutes away. When an astronaut falls ill, they cannot wait for Houston."*
  - Badges: `NASA Space Apps 2026 Karachi`, `100% Offline Edge Architecture`, `Mission: ARES-01 Mars Transit`.

#### Word-for-Word Spoken Script:
> *"Good afternoon, respected judge and fellow participants. We are Team AstraHealth, and we are proud to present **AstraHealth AI**: Autonomous Astronaut Health Intelligence for Long-Duration Space Missions.*
> 
> *Imagine you are an astronaut halfway to Mars on the ARES-01 mission. You wake up with unusual fatigue, subtle dizziness, and an elevated resting heart rate. Earth is 140 million miles behind you. At light-speed, a radio distress call to Mission Control in Houston takes up to 22 minutes to arrive, and another 22 minutes for advice to return.*
> 
> *In deep space, an astronaut experiencing a critical physiological anomaly cannot wait 44 minutes for telemedicine. They need real-time, trustworthy, and completely offline clinical self-reliance directly inside the habitat. That is why we engineered AstraHealth AI."*

---

### Slide 2: The Challenge & The Real Problem
- **Timing:** 0:50 – 1:50 (60 seconds)
- **Primary Criteria Target:** Relevance & Impact
- **Slide Visuals:**
  - 3 Core Dilemma Cards:
    1. **The 22-Minute Communication Void:** Mars latency prevents interactive telemedicine.
    2. **NASA's 5 Spaceflight Hazards:** Space radiation, isolation & confinement, distance from Earth, altered gravity (bone/muscle loss), and closed hostile environments.
    3. **The Fatal Flaw of Commercial AI:** Cloud dependency, hallucination risk, and reliance on terrestrial population averages.
  - Solution Highlight Box: What astronauts actually need (Personal dynamic baselines, deterministic safety rules, actionable care plans).

#### Word-for-Word Spoken Script:
> *"NASA’s Human Research Program groups the risks of exploration into Five Spaceflight Hazards: Radiation, Isolation, Distance, Gravity Alteration, and Hostile Closed Environments.*
> 
> *Now, why can't astronauts simply use modern commercial AI tools like ChatGPT or standard medical chatbots? For three critical reasons:*
> 
> *First, commercial AI requires constant internet and massive cloud servers—both are nonexistent on a Mars transit.*
> 
> *Second, commercial tools evaluate vitals against Earth population averages. But in microgravity, fluid shift to the upper body and cardiovascular remodeling make Earth averages misleading. What is normal for a terrestrial patient is abnormal in zero-g, and vice versa.*
> 
> *Third, and most dangerously: AI chatbots hallucinate. In aerospace medicine, an AI that invents a dosage or guesses a diagnosis is a mission-fatal risk.*
> 
> *Astronauts don't need a conversational chatbot guessing diseases. They need an intelligent edge system that understands their own personal baseline, guarantees deterministic safety, and gives them actionable steps to recover."*

---

### Slide 3: Modular Architecture — "Safety Before AI"
- **Timing:** 1:50 – 2:50 (60 seconds)
- **Primary Criteria Target:** Creativity & Validity
- **Slide Visuals:**
  - Architectural Flowchart:
    - `InputSense & DataGuard` (Multi-modal intake, negation detection: *"no chest pain"*, sensor sanity check).
    - `BaselineIQ` (Rolling personal baseline; crucially excludes the last 3 days to prevent baseline dilution).
    - `10 Specialist Agents` (CardioGuard, NeuroMind, SleepSense, BoneGuard, NutriTrack, MissionContext).
    - `Deterministic Safety & Evidence Gate` (Versioned rules assign severity: `NORMAL`, `MONITOR`, `REVIEW`, `URGENT`).
    - `Local Grounded LLM` (Runs on device, checked by a factual grounding guard).

#### Word-for-Word Spoken Script:
> *"To solve this, we architected AstraHealth around one fundamental engineering principle: **Safety Before AI.** Non-deterministic AI never decides patient triage.*
> 
> *Here is how our modular pipeline operates:*
> 
> *1. **InputSense & DataGuard** ingests both wearable telemetry and natural crew speech. If an astronaut reports 'tired, headache, no chest pain', it extracts the vitals, parses 'no chest pain' as a medical negation, and filters out sensor artifacts.*
> 
> *2. **BaselineIQ** establishes a personal dynamic baseline for each astronaut. Crucially, our algorithm excludes the most recent three days from the baseline window. Why? Because if a medical condition is developing over several days, including recent data would dilute the baseline and mask the illness.*
> 
> *3. **Specialist Agents** run in parallel across cardiovascular, neuro-cognitive, sleep, musculoskeletal, and nutritional domains.*
> 
> *4. **The Deterministic Safety Gate:** All agent outputs feed into an immutable, versioned medical rule set. Rules decide whether a status is Normal, Monitor, Review, or Urgent. If agents disagree, the system escalates—it never averages.*
> 
> *5. **Local Grounded LLM:** An optional offline AI writes plain-English explanations. But every single sentence is cross-checked against finding facts by our factual grounding guard, which strips any unverified claims."*

---

### Slide 4: Grounded on NASA & Space Agency Data
- **Timing:** 2:50 – 3:45 (55 seconds)
- **Primary Criteria Target:** Relevance & Validity
- **Slide Visuals:**
  - Logos / Badges of NASA Standards:
    - **NASA Human Research Roadmap (HRR):** SANS (Spaceflight-Associated Neuro-ocular Syndrome), bone deconditioning, sleep disruption.
    - **NASA-STD-3001 Volumes 1 & 2:** Official Space Flight Human-System Standard for crew health, nutrition thresholds, and exercise regimens.
    - **NASA Radiation Guidelines:** Active dosimeter thresholds and Solar Particle Event (SPE) emergency protocols.
    - **On-Device NASA Knowledge Base (KB-001 to KB-010):** Local BM25 & TF-IDF indexing of official NASA flight research. Transparent certainty grading (*Strong*, *Moderate*, *Limited*).

#### Word-for-Word Spoken Script:
> *"AstraHealth is not a generic wellness app with a space theme. It is built directly on official NASA standards and open space agency research.*
> 
> *We implemented clinical guidelines directly from **NASA-STD-3001 Volumes 1 and 2**, which define acceptable physiological limits, nutrition targets, and work-rest cycles for spaceflight.*
> 
> *We integrated evidence from the **NASA Human Research Roadmap**, specifically addressing Spaceflight-Associated Neuro-ocular Syndrome—or SANS—which causes optic disc swelling and vision changes due to intracranial fluid shifts in microgravity.*
> 
> *Furthermore, our application embeds a dedicated offline knowledge library—documents KB-001 through KB-010—indexed using local BM25 and TF-IDF search.*
> 
> *When AstraHealth flags an anomaly, it doesn't give a black-box opinion. It cites the exact NASA document passage and displays an honest certainty grade—telling the astronaut whether evidence is strong, moderate, or self-reported, and why."*

---

### Slide 5: The Astronaut User Experience & Workflow
- **Timing:** 3:45 – 4:50 (65 seconds)
- **Primary Criteria Target:** Creativity & Presentation
- **Slide Visuals:**
  - 4 UX Screen Highlights:
    1. **Conversational Check-In:** 30-second daily voice/text check-in with auto-extracted metrics.
    2. **Multi-Signal Anomaly Detection:** Graphs showing 7-day multi-parameter drift (HR up, sleep down, fatigue up).
    3. **Personalized Care Plan:** 5 concrete recovery tasks tied to baseline (not generic advice).
    4. **3D Digital Twin & Mission Routine:** Anatomical organ stress visualization and one-click scheduling of countermeasures into flight timeline.

#### Word-for-Word Spoken Script:
> *"Now let's examine the actual user experience for an astronaut during transit.*
> 
> *Every morning takes less than 30 seconds. The crew member checks in via voice or quick text. In our live test scenario, an astronaut submits: 'Tired and short on sleep, tight shoulders, no chest pain.'*
> 
> *Instead of panicking, AstraHealth correlates this with telemetry. While individual metrics might look borderline, our **multi-signal detector** flags gradual multi-day drift: resting heart rate has climbed 8 bpm, deep sleep has dropped 40%, and stress biomarkers are rising across seven days.*
> 
> *Here is our biggest breakthrough: **The Care Plan**. Most medical AI stops at a scary diagnosis. AstraHealth generates an actionable recovery roadmap tied to the astronaut's own baseline:*
> *- Goal: Restore sleep to their personal 6.6–7.7 hour window.*
> *- Step: Schedule a 30-minute protected wind-down window.*
> *- Step: Increase fluid intake by 500 mL.*
> 
> *With one click, the astronaut adds these tasks to their daily flight routine, and can inspect their physiological state on our interactive 2D and 3D Digital Twin."*

---

### Slide 6: Engineering Rigor, Security & Benchmarks
- **Timing:** 4:50 – 5:50 (60 seconds)
- **Primary Criteria Target:** Validity & Feasibility
- **Slide Visuals:**
  - Live Metric Grid:
    - **0.42s:** Full 11-step rule & ML pipeline execution latency.
    - **100% Offline:** Verified loopback-only network guard.
    - **79 / 79:** Backend Pytest test suite passed.
    - **28 / 28:** E2E Playwright tests & WCAG 2.2 AA accessibility audits passed.
    - **ML Stress Test:** Isolation Forest + CUSUM on 30 synthetic profiles under heavy-tailed noise (Precision 0.76, Recall 0.72, F1 0.74, FPR 5.4%).
  - Security Features: Windows DPAPI key protection, AES encryption of health text, SHA-256 hash-chained tamper-evident audit log.

#### Word-for-Word Spoken Script:
> *"Judges, AstraHealth AI is not a mockup or a slide-only concept. It is a fully operational, thoroughly tested engineering prototype.*
> 
> *On minimal edge hardware—a standard laptop with just 7.4 GB of RAM and zero GPU—our entire 11-step diagnostic pipeline finishes in just **0.42 to 0.60 seconds**.*
> 
> *Our machine learning model combines a NumPy Isolation Forest with rolling CUSUM change-point detection. We evaluated it across 30 synthetic astronaut profiles. Under rigorous stress testing with heavy-tailed sensor noise and circadian rhythms, it demonstrated an F1 score of **0.74** with an exceptionally low false-positive rate of **5.4%**.*
> 
> *We subjected the codebase to **79 backend automated tests** and **28 browser end-to-end flows**, including full WCAG 2.2 accessibility compliance for vision-impaired crew.*
> 
> *And for flight security: an automated network guard blocks all external network traffic. Sensitive medical notes are encrypted at rest with Windows DPAPI, and an immutable SHA-256 hash-chained audit log immediately detects any unauthorized data tampering."*

---

### Slide 7: Impact, Spin-Offs & Closing
- **Timing:** 5:50 – 7:00 (70 seconds)
- **Primary Criteria Target:** Impact & Presentation Climax
- **Slide Visuals:**
  - Dual Impact Columns:
    - **For Deep Space:** Solves the communication barrier; preserves astronaut health on Artemis Moon Base and Mars Transit.
    - **For Planet Earth:** Immediate spin-offs for remote polar stations, offshore oil rigs, deep-sea submarine crews, and rural clinics without internet.
  - The AstraHealth Core Motto (Callout Box):
    *"ASTRAHEALTH AI knows what changed against your baseline, how sure it is, and what to do next. Safety rules decide, and the AI only explains."*
  - Thank You & Q&A Transition Graphic.

#### Word-for-Word Spoken Script:
> *"In summary, AstraHealth AI delivers autonomous clinical self-reliance for the next era of human space exploration.*
> 
> *By shifting medical intelligence from Earth-bound servers to the spacecraft edge, we ensure that deep-space crews traveling to Mars or establishing lunar bases with Artemis are never left without immediate clinical guidance.*
> 
> *Furthermore, this innovation brings profound benefits to Planet Earth. The exact same offline, privacy-first technology can be deployed tomorrow on Antarctic research expeditions, offshore drilling platforms, naval submarines, and underserved rural clinics that lack reliable broadband internet.*
> 
> *We leave you with the foundational principle behind AstraHealth AI:*
> 
> ***'It knows what changed against your personal baseline, how sure it is, and what to do next. Safety rules decide, and the AI only explains.'***
> 
> *Thank you, judges. We are now delighted to answer your questions!"*

---

## 3. Judge Q&A Defense Playbook (3-Minute Master Guide)

Here are the highest-probability questions judges in Karachi will ask, mapped to the five evaluation criteria, with clear, authoritative answers:

### Criterion 1: Validity & Clinical Safety
#### Q1: "How do you ensure the AI does not hallucinate medical advice or prescribe dangerous treatments?"
> **Answer:**
> *"That is the core innovation of our architecture: **the LLM is completely decoupled from clinical triage.** Clinical severity—Normal, Monitor, Review, or Urgent—is calculated 100% deterministically by versioned, immutable rules based on NASA-STD-3001. The local LLM only synthesizes readable explanations. Moreover, every sentence generated by the LLM is evaluated by our post-generation Factual Grounding Guard. If the LLM generates a statement implying a diagnosis, medication, or unverified cause, that sentence is stripped automatically before the astronaut ever sees it."*

#### Q2: "What happens if an astronaut experiences a true medical emergency in flight?"
> **Answer:**
> *"If an urgent symptom is reported—such as crushing chest pain or acute neuro-deficit—the system immediately enters an `URGENT` lock state. In this state, self-care plans are completely suppressed. The system displays a persistent red alert directing the crew member to immediately notify the on-board Medical Officer. Furthermore, the astronaut cannot dismiss an urgent alert; clearing it or retracting the symptom requires authentication using the Medical Officer's dedicated cryptographic PIN."*

---

### Criterion 2: Creativity & Technical Architecture
#### Q3: "Why did you build your own Isolation Forest in NumPy instead of using Scikit-Learn or cloud APIs?"
> **Answer:**
> *"Flight systems operate under strict security policies. In our deployment environment, strict Application Control policies prevent compiling unverified external C-extensions. To guarantee 100% portability, zero internet reliance, and absolute predictability, we implemented the Isolation Forest, CUSUM, and BM25 search engines natively using pure NumPy and the Python standard library. This eliminated external dependencies, reduced memory footprint to under 2 GB, and cut execution time to just 420 milliseconds."*

#### Q4: "Why do you exclude the last 3 days from the astronaut's baseline window?"
> **Answer:**
> *"If an astronaut begins experiencing slow physiological decline—like creeping dehydration or microgravity cardiovascular deconditioning over 5 days—a standard rolling average would absorb those abnormal values into the baseline. The abnormal values would then appear 'normal.' By lagging the baseline window by 3 days, our baseline maintains a clean historical reference, allowing our rolling CUSUM and z-score detectors to reliably catch gradual drift."*

---

### Criterion 3: Relevance & Space Agency Data
#### Q5: "What specific NASA datasets or space agency standards did you use?"
> **Answer:**
> *"We utilized three primary NASA resources: First, **NASA-STD-3001 Volumes 1 and 2** (Space Flight Human-System Standard) for our clinical severity thresholds, nutritional boundaries, and exercise countermeasures. Second, the **NASA Human Research Roadmap (HRR)**, specifically the Spaceflight-Associated Neuro-ocular Syndrome (SANS) research dataset and microgravity cardiovascular metrics. Third, the **NASA Human Research Program (HRP) Five Spaceflight Hazards framework**. We indexed these into a local on-device knowledge base (KB-001 through KB-010) so every recommendation cites real NASA literature."*

---

### Criterion 4: Impact & Feasibility
#### Q6: "Can this system actually run on actual spacecraft computers, which often have limited processing power?"
> **Answer:**
> *"Yes, absolutely. Deep-space radiation-hardened flight computers prioritize reliability over raw GPU compute. We specifically benchmarked AstraHealth on a low-spec CPU-only machine with just 7.4 GB of RAM. The entire multi-agent diagnostic rule engine executes in under half a second (0.42s). The local LLM explanation runs asynchronously in the background without blocking alerts. If resources are constrained, the LLM can be disabled entirely, and AstraHealth will seamlessly display instant, deterministic template explanations without losing any clinical functionality."*

#### Q7: "How is astronaut data privacy protected among crew members sharing the same habitat terminal?"
> **Answer:**
> *"Astronaut medical logs are highly sensitive. AstraHealth enforces three layers of security: First, all free-text notes and conversational journals are encrypted at rest with AES, wrapped via Windows DPAPI. Second, distinct role-based PINs separate crew members from the Medical Officer and System Administrator, with automated lockout cooldowns after five failed attempts. Third, an immutable SHA-256 hash-chained audit log records every access, edit, or retraction, ensuring complete tamper detection."*

---

## 4. Final 5-Minute Pre-Presentation Rehearsal Checklist

Before walking up to the judging table:
- [ ] **1. Open the Presentation Deck:** Double-click [`docs/NSAC_Karachi_Presentation_7_Slides.html`](file:///c:/Users/hadia/AstraHealth%20AI/docs/NSAC_Karachi_Presentation_7_Slides.html) in Microsoft Edge or Chrome. Press `F` to enter full-screen mode.
- [ ] **2. Turn Wi-Fi Completely OFF:** Proves to the judge right away that this is an air-gapped offline system.
- [ ] **3. Have Background Server Running:** Run `scripts\start.ps1` in PowerShell. Verify http://127.0.0.1:8765 loads in a background tab if the judge asks for a live walkthrough.
- [ ] **4. Time Check:** Start the presentation timer on Slide 1 (or click the built-in timer button `▶`). Target finishing Slide 7 at 6:30 to 6:45 so you never get cut off by the judge.
- [ ] **5. Keep the Closing Line Crisp:** *"Safety rules decide, and the AI only explains."* End with high energy and invite their questions immediately.

