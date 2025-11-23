# Azure Function: SAS URL Generator for Blob Storage

This Azure Function provides a secure, short-lived SAS (Shared Access Signature) URL for uploading files directly to Azure Blob Storage. It's designed to work with a frontend application that needs to upload evidence files without exposing storage credentials.

## Overview

This function has a single, focused responsibility:

- **Generate write-only SAS URLs** for uploading files to the `/uploads` container in Azure Blob Storage
- **No file processing** - it only generates URLs
- **No writing to `/evidence`** - that's handled by your existing blob trigger
- **No SmartAI BE calls** - purely a SAS URL issuer
- **Secure** - uses Managed Identity, no storage keys stored anywhere

## Architecture

```
┌─────────┐    1. POST /upload/sas      ┌──────────────┐
│   FE    │ ──────────────────────────> │   Function   │
│         │    { sid, label, filename } │              │
└─────────┘                             └──────────────┘
     │                                          │
     │    2. Returns { uploadUrl }              │
     │<─────────────────────────────────────────┘
     │
     │    3. PUT uploadUrl (binary file)
     │    ──────────────────────────────────────┐
     │                                          │
     │                                          ▼
     │                                  ┌──────────────┐
     │                                  │ Blob Storage │
     │                                  │  /uploads    │
     │                                  └──────────────┘
     │                                          │
     │                                          │ 4. Blob trigger fires
     │                                          ▼
     │                                  ┌────────────────┐
     │                                  │evidence_extract│
     │                                  │  (existing)    │
     │                                  └────────────────┘
     │                                          │
     │                                          │ 5. Writes to /evidence
     │                                          ▼
     │                                  ┌──────────────┐
     │                                  │  /evidence   │
     │                                  └──────────────┘
     │
     │
     │ 6. GET /v1/debug/evidence/{sid}?preview=120
     │ ──────────────────────────────────────────────>
     │                  SmartAI BE
     │
```

## API Endpoint

### `POST /upload/sas`

Generates a short-lived SAS URL for uploading a single file to blob storage.

**Request:**
```json
{
  "sid": "s_12345",
  "label": "invoice",
  "filename": "invoice.pdf"
}
```

**Response (200 OK):**
```json
{
  "uploadUrl": "https://<account>.blob.core.windows.net/uploads/s_12345_invoice.pdf?<sas-token>",
  "blobName": "s_12345_invoice.pdf",
  "expiresInMinutes": 10
}
```

**Error Responses:**
- `400 Bad Request` - Invalid input (e.g., invalid characters in sid, label, or filename)
- `500 Internal Server Error` - Server error (check logs for details)

**Input Validation:**
- `sid`, `label`, and `filename` must match pattern: `^[a-zA-Z0-9_\-\.]+$`
- All fields are required and cannot be empty

**Blob Naming Convention:**
- Format: `{sid}_{label}{ext}`
- Example: `s_12345_invoice.pdf` → blob name: `s_12345_invoice.pdf`
- Extension is preserved from filename, defaults to `.pdf` if missing

## Environment Variables

Required environment variables for the Azure Function App:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORAGE_ACCOUNT_NAME` | Yes | - | Azure Storage account name |
| `UPLOADS_CONTAINER` | No | `uploads` | Container name for uploads |
| `SAS_TTL_MINUTES` | No | `10` | SAS URL expiration time in minutes |

## Local Development

### Prerequisites

- Python 3.10+
- Azure Functions Core Tools v4
- Azure CLI (for authentication)

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd sgdev-smartai-func-sas
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables:**
   
   Create a `local.settings.json` file (not committed to git):
   ```json
   {
     "IsEncrypted": false,
     "Values": {
       "AzureWebJobsStorage": "UseDevelopmentStorage=true",
       "FUNCTIONS_WORKER_RUNTIME": "python",
       "STORAGE_ACCOUNT_NAME": "your-storage-account",
       "UPLOADS_CONTAINER": "uploads",
       "SAS_TTL_MINUTES": "10"
     }
   }
   ```

5. **Run locally:**
   ```bash
   func start
   ```

### Testing the Endpoint

```bash
curl -X POST http://localhost:7071/api/upload/sas \
  -H "Content-Type: application/json" \
  -d '{
    "sid": "s_12345",
    "label": "invoice",
    "filename": "invoice.pdf"
  }'
```

## Deployment

### GitHub Actions (Automatic)

The repository includes a GitHub Actions workflow that automatically deploys on push to `main`:

1. **Configure GitHub Secrets:**
   - `AZUREAPPSERVICE_CLIENTID_SAS` - Azure App Service client ID
   - `AZUREAPPSERVICE_TENANTID_SAS` - Azure tenant ID
   - `AZUREAPPSERVICE_SUBSCRIPTIONID_SAS` - Azure subscription ID

2. **Push to main branch:**
   ```bash
   git push origin main
   ```

   The workflow will:
   - Build the function
   - Create a deployment package
   - Deploy to Azure Function App `sgdev-smartai-func-sas`

### Manual Deployment

1. **Install Azure Functions Core Tools:**
   ```bash
   npm install -g azure-functions-core-tools@4
   ```

2. **Login to Azure:**
   ```bash
   az login
   ```

3. **Deploy:**
   ```bash
   func azure functionapp publish sgdev-smartai-func-sas
   ```

## Security

- **Managed Identity**: Uses `DefaultAzureCredential` for authentication
- **User Delegation SAS**: Generates SAS tokens using user delegation keys (no storage account keys)
- **Input Validation**: Strict regex validation prevents path injection attacks
- **Short-lived URLs**: SAS URLs expire after 10 minutes (configurable)
- **Write-only Permissions**: SAS tokens only grant `write`, `create`, and `add` permissions

## File Structure

```
sgdev-smartai-func-sas/
├── .github/
│   └── workflows/
│       └── main_sgdev-smartai-func-sas.yml  # GitHub Actions deployment
├── function_app.py                           # Main function code
├── host.json                                 # Azure Functions host config
├── requirements.txt                          # Python dependencies
├── .gitignore                                # Git ignore patterns
└── README.md                                 # This file
```

## Dependencies

- `azure-functions>=1.20.0` - Azure Functions runtime
- `azure-identity==1.17.1` - Azure authentication (Managed Identity)
- `azure-storage-blob==12.19.1` - Azure Blob Storage SDK

## Integration Flow

1. **Frontend requests SAS URL:**
   ```javascript
   const response = await fetch('https://<function-app>.azurewebsites.net/api/upload/sas', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       sid: 's_12345',
       label: 'invoice',
       filename: 'invoice.pdf'
     })
   });
   const { uploadUrl, blobName } = await response.json();
   ```

2. **Frontend uploads file directly to blob storage:**
   ```javascript
   await fetch(uploadUrl, {
     method: 'PUT',
     body: fileBlob,
     headers: { 'x-ms-blob-type': 'BlockBlob' }
   });
   ```

3. **Existing blob trigger processes the file:**
   - Your `evidence_extract` function triggers on `/uploads/{name}`
   - Processes the file and writes to `/evidence/{sid}_{label}.txt`

4. **Frontend refreshes evidence list:**
   ```javascript
   await fetch(`https://<smartai-be>/v1/debug/evidence/${sid}?preview=120`);
   ```

## Troubleshooting

### Common Issues

1. **"Invalid sid/label/filename" error:**
   - Ensure all fields contain only alphanumeric characters, underscores, hyphens, and dots
   - No spaces or special characters allowed

2. **"STORAGE_ACCOUNT_NAME not set" error:**
   - Verify environment variable is set in Azure Function App Configuration
   - Check `local.settings.json` for local development

3. **SAS URL expires too quickly:**
   - Adjust `SAS_TTL_MINUTES` environment variable
   - Default is 10 minutes

4. **Deployment fails:**
   - Check GitHub Actions logs
   - Verify all required secrets are configured
   - Ensure Function App exists and Managed Identity is enabled

## License

[Add your license here]

## Contributing

[Add contributing guidelines if applicable]

