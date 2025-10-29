# URL Generator DPP

## Step-by-Step Instructions

1. **Install dependencies:**
   ```bash
   pip install pandas openpyxl
   ```

2. **Place Excel files in this folder:**
   - Matching pairs: `<name>_eans.xlsx` and `<name>_orders.xlsx`
   - Example: `test-name-1_eans.xlsx` + `test-name-1_orders.xlsx`

3. **Excel file formats:**
   - **Orders file** (`*_orders.xlsx`):
     - Column A: `purchase_order`
     - Column B: `product`
     - Column C: `base_url`
   - **EANs file** (`*_eans.xlsx`):
     - Column A: `product` (repeats for each EAN)
     - Column B: `ean`

4. **Run the script:**
   ```bash
   python generate_urls.py
   ```

5. **Output:**
   - Creates `<name>_urls.xlsx` for each pair found
   - URL format: `base_url/01/{ean}/10/{purchase_order}`
   - Includes sheet: `urls` (main output) and `unmatched_orders` (if any products without EANs)

