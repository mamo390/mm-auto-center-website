# M&M Auto Center - n8n Workflows

## Workflows Included

### 1. Instagram Auto Post
**File:** `instagram-auto-post.json`

**What it does:**
- Runs every 3 days (72 hours)
- Reads content calendar from Google Sheets
- Finds posts scheduled for today with Status = "Pending"
- Posts to Instagram via Zapier MCP
- Updates status to "Posted" in Google Sheets

**Setup Instructions:**

### Step 1: Import Workflow
1. Open n8n UI: http://localhost:5678
2. Click "Workflows" → "Import from File"
3. Select `instagram-auto-post.json`

### Step 2: Configure Credentials

#### Google Sheets OAuth2:
1. Go to Settings → Credentials
2. Add New: Google Sheets OAuth2
3. Follow OAuth flow to authorize
4. Copy Sheet ID from your Excel file URL

#### Zapier MCP Client:
1. Go to Settings → Credentials
2. Add New: MCP Client
3. Name: "Zapier MCP"
4. Base URL: `https://mcp.zapier.com/api/v1/connect`
5. Auth Token: `NWE4YWI5MTUtMjYzNy00NDVlLTgyYTMtY2E3ZGJlYWQ2OWQ5OmRkMkVXdEErNGpjckU3K1hMYk94eC9QczVJQ095R2VWblM2WDVBV1pRaDA9`

### Step 3: Set Environment Variables
```bash
export MM_GOOGLE_SHEET_ID="your-google-sheet-id-here"
```

### Step 4: Upload Images
Images must be publicly accessible URLs. Options:
1. Upload to Google Drive (public)
2. Use Cloudinary
3. Use GitHub raw URLs

### Step 5: Activate Workflow
1. Open the workflow
2. Click "Active" toggle
3. Test manually first

## Troubleshooting

### n8n not starting:
```bash
ps aux | grep n8n  # Check if running
killall node        # Kill if stuck
n8n start           # Restart
```

### MCP Server not accessible:
- Check port 5678 is open
- Verify environment variables are set
- Check n8n logs: `tail -f /tmp/n8n.log`

### Instagram posting fails:
- Verify Zapier MCP OAuth is complete
- Check image URLs are publicly accessible
- Review Instagram Business account connection