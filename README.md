# Lorelei – Studio Invoice Generator

## 1. Project Title and Description

Lorelei is a Streamlit application that generates monthly employee invoices from Google Calendar booking data and produces an AI-generated management report.

The application was built for a local game studio that bills employees for room rentals on a monthly basis. (The name "Lorelei" is a play on the studio's name.) The AI report uses OpenAI's GPT-5 Mini model to transform booking statistics into a manager-friendly narrative containing trends, observations, and recommendations.

---

## 2. Problem Statement

Problem: Currently, the studio's billing process requires staff to manually review Google Calendar bookings, calculate rental fees, and create invoices for each employee. This workflow is repetitive and time-consuming. 

Solution: Lorelei automates invoice generation and provides AI-generated analysis to help managers quickly understand monthly activity and trends.

---

## 3. Technology Stack

### Language

* Python

### Libraries

* Streamlit
* pandas
* icalendar
* recurring-ical-events
* reportlab
* python-dotenv
* openai

### AI API

* OpenAI API (GPT-5 Mini)

---

## 4. Setup Instructions

1. Clone the repository.

```bash
git clone <repository-url>
cd <repository-folder>
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create a `.env` file from `.env.example` and add your API key.

```text
OPENAI_API_KEY=your_api_key_here
```

4. Run the application.

```bash
streamlit run app.py
```

---

## 5. Usage Examples

### Example 1 – Invoice Generation

**Input:** Upload up to 4 monthly Google Calendar `.ics` file (one calendar per room).

**Output:** PDF invoices for each employee and separate downloadable .csv files of sessions and fees/credits.

### Example 2 – AI Report

**Input:** Click **Generate AI Report** after processing calendar data.

**Output:** Monthly statistics, employee and game rankings, utilization insights, and an AI-generated management summary with recommendations.

---

## 6. Known Limitations

1. The AI report sends employee names and session data to an external cloud AI service. Future versions may anonymize data or support a local language model.

2. The application does not save project state. If the user closes the application, invoice generation must be repeated from the original calendar data.

---

## 7. Future Improvements

1. Expand the AI report with additional analytics and recommendations based on studio feedback. Anonymize data or support a local language model.

2. Develop **Re-Lorelei**, a companion application that regenerates invoices directly from exported CSV files, allowing users to correct historical records or regenerate invoices without re-importing calendar data and starting again from scratch.
