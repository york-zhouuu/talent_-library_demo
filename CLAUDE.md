# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Talent Library System** - An intelligent talent/candidate management system with AI-powered search and CKB (Candidate Knowledge Base) architecture. Designed for recruitment and talent management with integration for AI agents via MCP (Model Context Protocol).

## Build & Development Commands

### Backend (Python/FastAPI)
```bash
# Install dependencies
pip install -e .
pip install -e ".[dev]"    # Include dev dependencies

# Run development server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest

# Run linter
ruff check app/

# Database migrations
alembic upgrade head                           # Apply migrations
alembic revision --autogenerate -m "message"   # Create new migration
```

### Frontend (React/TypeScript)
```bash
cd frontend

# Install dependencies
npm install

# Development server (port 3000)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Docker Services
```bash
# Start PostgreSQL + Redis
docker-compose up -d
```

### Full System Startup
```bash
./start.sh   # Starts both backend and frontend
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.11+), Uvicorn, SQLAlchemy 2.0 async |
| Frontend | React 18, TypeScript, Vite, TanStack Query, Tailwind CSS |
| Database | SQLite (dev) / PostgreSQL + pgvector (prod) |
| Cache | Redis 7.0 |
| AI | Anthropic Claude API (claude-sonnet-4-5-20250929) |
| File Processing | PyPDF2, python-docx, pdf2image (OCR fallback) |

## Architecture

### Project Structure
```
project/
├── app/                      # Backend Python application
│   ├── main.py               # FastAPI app entry point
│   ├── api/v1/               # REST API endpoints
│   │   ├── candidates.py     # Candidate CRUD
│   │   ├── talent_pools.py   # Pool management
│   │   ├── search.py         # Search endpoints
│   │   ├── tags.py           # Tag management
│   │   ├── skill/            # Skill-based APIs
│   │   └── agent/            # Agent-specific endpoints
│   ├── models/candidate.py   # SQLAlchemy ORM models
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/             # Business logic layer
│   │   ├── ai_service.py     # Claude API integration
│   │   ├── ckb_service.py    # CKB 4-layer management
│   │   ├── search_service.py # Intelligent search
│   │   ├── resume_parser.py  # Resume extraction
│   │   └── router_service.py # Search routing
│   ├── db/                   # Database session & Redis
│   └── core/                 # Config & exceptions
├── frontend/src/             # React TypeScript SPA
│   ├── pages/                # Search, Upload, TalentPools, PoolDetail
│   ├── components/           # Reusable components
│   └── services/api.ts       # API client
├── mcp_server/               # MCP server for AI agents
├── alembic/                  # Database migrations
└── docker-compose.yml        # PostgreSQL + Redis
```

### CKB 4-Layer Information Architecture
| Layer | Purpose | Data |
|-------|---------|------|
| Layer 1 | Raw Data | Base resume info (Candidate model) |
| Layer 2 | Derived Profile | AI-generated insights, skills, summary |
| Layer 3 | Accumulated Knowledge | Human-verified data, status, feedback |
| Layer 4 | Session Context | Ephemeral search-specific analysis |

**Priority Resolution:** Layer 3 (human) > Layer 1 (raw) > Layer 2 (AI-derived)

### Key Data Models
- **Candidate** - Core candidate info, skills, embedding
- **CandidateProfile** - AI-derived Layer 2 profile
- **CandidateKnowledge** - Human Layer 3 knowledge
- **TalentPool** - Pool with sharing mechanism
- **Resume** - Uploaded files with parsed data
- **Tag** - Categorization tags

## API Endpoints (Base: `/api/v1`)

### Candidates
- `POST /candidates` - Create candidate
- `GET /candidates` - List (paginated)
- `GET /candidates/{id}` - Get details
- `POST /candidates/import` - Import single resume
- `POST /candidates/import/batch` - Batch import
- `POST /candidates/{id}/profile/generate` - Generate AI profile
- `GET /candidates/{id}/profile` - Get Layer 2 profile
- `GET /candidates/{id}/knowledge` - Get Layer 3 knowledge

### Talent Pools
- `POST /talent-pools` - Create pool
- `GET /talent-pools` - List pools
- `POST /talent-pools/{id}/candidates` - Add candidate
- `POST /talent-pools/{id}/shares` - Share pool

### Search
- `POST /search/natural/stream` - Streaming intelligent search (SSE)
- `POST /search/intelligent` - Full intelligent search
- `POST /search/quick` - Quick direct search

### MCP Server Tools
- `talent_search` - Natural language search
- `talent_get_candidate` - Get candidate details
- `talent_list_pools` - List pools
- `talent_add_to_pool` / `talent_remove_from_pool` - Pool operations
- `talent_update_status` - Update candidate status
- `talent_add_note` - Add recruitment notes

## Configuration

### Environment Variables (.env)
```
DATABASE_URL=sqlite+aiosqlite:///./talent_library.db
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=your-api-key
APP_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=10485760
```

## Key Implementation Notes

1. **Async Throughout** - Full async/await with SQLAlchemy asyncio
2. **Smart Resume Extraction** - Text extraction with OCR fallback for image PDFs
3. **Streaming Search** - Real-time status via Server-Sent Events (SSE)
4. **Chinese Name Support** - Regex-based extraction from filenames
5. **Vector-Ready** - Embedding field prepared for pgvector
6. **Multi-User** - User ID tracking in headers, per-user pool creation
7. **CORS** - Configured for localhost:3000 (frontend)
