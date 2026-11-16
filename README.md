# 🤖 AI-Powered Database Assistant

An AI-powered Natural Language to SQL Query Generator that allows users to interact with a student database using simple English questions.

## 🚀 Live Demo

[Open AI Database Assistant](https://isharawat-01-ai-database-assistant-app-i5wnvv.streamlit.app/)

## 📌 Project Overview

This project converts natural language questions into SQL queries using Google's Gemini AI. It uses Retrieval-Augmented Generation (RAG) with Qdrant to retrieve database schema information and SQLite to execute the generated SQL queries.

The application also provides an interactive dashboard for analyzing student records.

## ✨ Features

- Natural Language to SQL Query Generation
- Gemini AI Integration
- RAG-based Schema Retrieval
- Qdrant Vector Database
- SQLite Database Integration
- Interactive Streamlit Dashboard
- Course-wise Student Analysis
- City-wise Student Analysis
- Active vs Inactive Student Visualization
- Read-only SQL Query Execution

## 🛠️ Technologies Used

| Technology | Purpose |
|---|---|
| Python | Core programming language |
| Streamlit | Web application and dashboard |
| Google Gemini AI | SQL query generation |
| Qdrant | Vector database |
| RAG | Schema retrieval |
| SQLite | Database management |
| Pandas | Data processing |
| Plotly | Data visualization |

## 🏗️ Project Workflow

1. User enters a question in natural language.
2. Gemini generates an embedding for the question.
3. Qdrant retrieves the relevant database schema.
4. Gemini generates an SQL query using the retrieved schema.
5. SQLite executes the read-only SQL query.
6. Results are displayed on the Streamlit dashboard.

## 📂 Project Structure

```text
AI-Database-Assistant/
│
├── app.py
├── main.py
├── create_database.py
├── embed_schema.py
├── retrieve_schema.py
├── generate_sql.py
├── execute_sql.py
├── schema.md
├── students.db
├── requirements.txt
└── .gitignore
```

## ⚙️ Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/isharawat-01/AI-Database-Assistant.git
```

### 2. Navigate to the project folder

```bash
cd AI-Database-Assistant
```

### 3. Create a virtual environment

```bash
python -m venv venv
```

### 4. Activate the virtual environment

Windows:

```bash
venv\Scripts\activate
```

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

### 6. Configure Gemini API Key

Create a `.env` file in the project directory:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Never upload your API key to GitHub.

### 7. Run the application

```bash
streamlit run app.py
```

## 📊 Dashboard

The dashboard displays:

- Total number of students
- Active students
- Inactive students
- MCA students
- Course-wise distribution
- City-wise distribution
- Student status distribution

## 🔮 Future Scope

- Support for multiple database systems
- More advanced schema retrieval
- Improved query validation
- Query history and analytics
- Enhanced dashboard visualizations

## 👩‍💻 Author

**Isha Rawat**

MCA Student | Python | SQL | Data Analysis | AI

GitHub: [isharawat-01](https://github.com/isharawat-01)

---

⭐ If you find this project useful, consider giving the repository a star!