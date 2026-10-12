"""Shared configuration for K4 / Track 3B: Eval + Guardrail Stack."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")  # Optional: for HuggingFace models

# --- OpenAI-compatible gateway (Day 18 modules m4/m5 read these) ---
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "").strip() or "text-embedding-3-small"
# Model reasoning tiêu token suy luận trước khi sinh content → cần cộng thêm budget.
REASONING_TOKEN_BUDGET = int(os.getenv("REASONING_TOKEN_BUDGET", "0"))

# --- RAGAS ---
# RAGAS mặc định 16 workers đồng thời → gateway dễ bị quá tải → metric NaN.
RAGAS_MAX_WORKERS = int(os.getenv("RAGAS_MAX_WORKERS", "2"))
RAGAS_TIMEOUT = int(os.getenv("RAGAS_TIMEOUT", "600"))
RAGAS_MAX_TOKENS = int(os.getenv("RAGAS_MAX_TOKENS", "8192"))

if OPENAI_BASE_URL:  # openai SDK tự đọc 2 biến này
    os.environ.setdefault("OPENAI_BASE_URL", OPENAI_BASE_URL)
    os.environ.setdefault("OPENAI_API_BASE", OPENAI_BASE_URL)

# --- Qdrant (same as Day 18) ---
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "lab24_production"
NAIVE_COLLECTION = "lab24_naive"

# --- Embedding (same as Day 18) ---
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

# --- Chunking (same as Day 18) ---
HIERARCHICAL_PARENT_SIZE = 2048
HIERARCHICAL_CHILD_SIZE = 256
SEMANTIC_THRESHOLD = 0.85

# --- Search (same as Day 18) ---
BM25_TOP_K = 20
DENSE_TOP_K = 20
HYBRID_TOP_K = 20
RERANK_TOP_K = 3

# --- Paths ---
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
FIXTURES_DIR = os.path.join(ROOT_DIR, "fixtures")
ARTIFACTS_DIR = os.path.join(ROOT_DIR, "artifacts")
TEST_SET_PATH = os.path.join(FIXTURES_DIR, "test_set_50q.json")
ANSWERS_PATH = os.path.join(ARTIFACTS_DIR, "answers_50q.json")
HUMAN_LABELS_PATH = os.path.join(FIXTURES_DIR, "human_labels_10q.json")
ADVERSARIAL_SET_PATH = os.path.join(FIXTURES_DIR, "adversarial_set_20.json")
CLEAN_SET_PATH = os.path.join(FIXTURES_DIR, "clean_set_8.json")
OUTPUT_SET_PATH = os.path.join(FIXTURES_DIR, "output_set_4.json")
GUARDRAILS_CONFIG_DIR = os.path.join(ROOT_DIR, "guardrails")
PAIR_QUESTION_IDS = (1, 5, 12, 21, 41)

# --- LLM Judge ---
# Gateway của lớp (ai-box) không có kênh gpt-4o-mini; dùng model khả dụng.
# generation/evaluator/judge tách vai trò nhưng cùng model ở môi trường này.
GENERATION_MODEL = OPENAI_MODEL
JUDGE_MODEL = OPENAI_MODEL

# --- Guardrail latency budget ---
LATENCY_BUDGET_P95_MS = 500  # Full guard target; Task 12 currently measures input guards only.
PRESIDIO_LANGUAGE = "en"    # Presidio base language; custom VN recognizers added via PatternRecognizer
