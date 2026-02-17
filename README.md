# VN-Stock Monitor

Dashboard theo dõi thị trường chứng khoán Việt Nam với **FastAPI (backend)** + **Streamlit (frontend)**, sử dụng thư viện **vnstock** (ưu tiên nguồn **KBS**, fallback **VCI**).

## 1) Yêu cầu

- Python 3.10+
- API key vnstock (Free tier)

## 2) Cấu hình (không hard-code API key)

Tạo file `.env` ở thư mục gốc repo (hoặc export env vars), dựa theo `.env.example`.

Ví dụ `.env`:

```env
VNSTOCK_API_KEY=YOUR_KEY_HERE
ALLOWED_ORIGINS=http://localhost:8501
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

## 3) Chạy Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# load env (PowerShell)
setx VNSTOCK_API_KEY "YOUR_KEY_HERE"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check: `GET http://localhost:8000/health`

## 4) Chạy Frontend (Streamlit)

```bash
cd streamlit_app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

setx BACKEND_BASE_URL "http://localhost:8000"
streamlit run app.py
```

Mở trình duyệt: `http://localhost:8501`

## 5) Ghi chú quan trọng

- Không dùng TCBS (đã deprecated).
- Có caching TTL phía backend để giảm rate limit.
- Tab News lấy từ các nguồn: cafef, tinnhanhchungkhoan, vnexpress, vietstock (VN), bloomberg (quốc tế) qua endpoint `GET /api/news/latest`.

## 6) Verification & Runbook

### 6.1 Kiểm tra nhanh backend/frontend

- **Health check backend**: `curl http://localhost:8000/health` → kỳ vọng `{"status":"ok"}`.
- **API key vnstock**: đảm bảo biến môi trường `VNSTOCK_API_KEY` đã được set **trước khi** khởi động backend.
- **Kết nối frontend → backend**:
  - Mở `http://localhost:8501`.
  - Nếu có lỗi kết nối, kiểm tra env `BACKEND_BASE_URL` và `ALLOWED_ORIGINS`.

### 6.2 Trading hours & hành vi dữ liệu

- Dữ liệu realtime (price board, quote) chỉ cập nhật trong giờ giao dịch (khoảng 9:00–15:00 giờ Việt Nam).
- Ngoài giờ giao dịch, các endpoint realtime vẫn trả về snapshot gần nhất, kèm thời gian `as_of` trong payload.
- Dữ liệu lịch sử (history) không phụ thuộc giờ giao dịch; nếu khoảng thời gian không có phiên, chuỗi có thể bị “rỗng” hoặc thưa.

### 6.3 Cache TTL (backend)

Các TTL hiện tại (xem `backend/app/services/vnstock_service.py` và `backend/app/services/news_service.py`):

- **Market cards / top movers / indices**: 60s.
- **Stock list** (`/api/stocks/list`): 12h.
- **Stock quote** (`/api/stock/{symbol}/quote`) và **price board** (`/api/market/price-board`): 15s.
- **History** (`/api/stock/{symbol}/history`): 120s.
- **Company news theo mã** (`/api/stock/{symbol}/news`): 600s.
- **News feed toàn thị trường** (`/api/news/latest`): 300s.

Trong quá trình QA, nếu thấy dữ liệu chậm cập nhật, kiểm tra xem có đang nằm trong TTL cache hay không trước khi kết luận lỗi nguồn dữ liệu.

### 6.4 Rate limit vnstock

- Free tier: khoảng **20 request/phút**, có thể lên tới **60 request/phút** khi dùng API key đúng cấu hình.
- Backend đã bắt `RateLimitException` và trả HTTP `429` với thông điệp rõ ràng.
- Khi test thủ công, ưu tiên:
  - Dùng ít endpoint, tận dụng cache TTL.
  - Không gửi quá nhiều request lặp lại cho cùng symbol/universe trong thời gian ngắn.

### 6.5 Lỗi thường gặp & cách xử lý

- **HTTP 429 (Rate limit)**:
  - Giảm tần suất gọi, xem lại batch size (ví dụ `universe` quá rộng).
  - Chờ thêm 1–2 phút rồi thử lại; nếu tái diễn, kiểm tra cấu hình API key và tier.
- **HTTP 404 (Symbol not found / Profile not found)**:
  - Đảm bảo mã viết hoa và đúng sàn (HOSE/HNX/UPCOM).
  - Kiểm tra lại trong danh sách `/api/stocks/list?exchange=...`.
- **History rỗng / thiếu điểm**:
  - Có thể symbol mới niêm yết hoặc delist.
  - Với index proxy: nếu `VNINDEX` trống, backend tự fallback sang `VN30` (endpoint `/api/market/indices`).
- **News ít hoặc trống**:
  - Một số nguồn RSS / HTML có thể thay đổi cấu trúc tạm thời; thử đổi `region`/`sources` với `/api/news/latest`.
  - Với news theo mã, có thể mã ít tin tức trong khoảng thời gian gần.

### 6.6 Sanity-check end-to-end flows

- **Flow Dashboard**:
  - Mở trang `Dashboard` trong Streamlit.
  - Xác nhận các thẻ thị trường (VN30, HNX30, …) hiển thị giá trị và % thay đổi hợp lý.
  - Kiểm tra biểu đồ chỉ số (VNINDEX hoặc proxy VN30) hiển thị dữ liệu 1 tháng gần nhất.
  - Nếu nghi ngờ, gọi trực tiếp:
    - `GET http://localhost:8000/api/market/indices`
    - `GET http://localhost:8000/api/market/top-movers?type=gainers&universe=VN30&limit=10`
- **Flow Market list**:
  - Vào tab `Market`, chọn sàn (HOSE/HNX/UPCOM).
  - Bảng phải load danh sách mã; so sánh nhanh với `GET /api/stocks/list?exchange=HOSE`.
  - Click vào một mã bất kỳ → được điều hướng sang trang `Stock Detail` tương ứng.
- **Flow Stock Detail**:
  - Tìm một mã thanh khoản lớn (ví dụ `VCB`, `FPT`, `SSI`) từ ô tìm kiếm.
  - Kiểm tra:
    - Biểu đồ nến / line xuất hiện (từ `/api/stock/{symbol}/history`).
    - Giá hiện tại / thay đổi ngày (`/api/stock/{symbol}/quote`).
    - Thông tin cơ bản và ratios (`/api/stock/{symbol}/profile`, `/api/stock/{symbol}/financial/ratios`).
- **Flow News**:
  - Tab `News`:
    - Với feed toàn thị trường: kiểm tra `GET /api/news/latest?region=vn&limit=50`.
    - Với news theo mã: kiểm tra `GET /api/stock/{symbol}/news?limit=20`.
  - Đảm bảo có ít nhất một số tin mới, link mở được và tiêu đề hợp lý.

Nếu toàn bộ các flow trên hoạt động ổn định trong giờ giao dịch và ngoài giờ (với dữ liệu snapshot), hệ thống có thể coi là **pass sanity-check** cho môi trường local/prod.
