## Setup Instructions

### Backend Setup
1. Clone the repository
2. Create virtual environment: `python -m venv venv`
3. Activate: `venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. **Copy `.env.example` to `.env`** (optional - uses defaults)
6. Start server: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`

### Frontend Setup
1. Navigate to frontend: `cd frontend`
2. Install dependencies: `npm install`
3. **Copy `.env.example` to `.env`** (optional - uses defaults)
4. Start development server: `npm start`