import logging, os, json, re

from datetime import datetime, timedelta, timezone

import azure.functions as func

from azure.identity import DefaultAzureCredential

from azure.storage.blob import (

    BlobServiceClient,

    generate_blob_sas,

    BlobSasPermissions

)

app = func.FunctionApp()

SAFE_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

def _safe(s: str, field: str) -> str:

    if not s or not SAFE_RE.match(s):

        raise ValueError(f"Invalid {field}")

    return s

@app.route(route="upload/sas", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)

def issue_sas(req: func.HttpRequest) -> func.HttpResponse:

    """

    POST /upload/sas

    body: { sid, label, filename }

    returns:

      {

        uploadUrl: "<one-blob SAS URL>",

        blobName: "<sid>_<label>.<ext>",

        expiresInMinutes: 10

      }

    """

    try:

        body = req.get_json()

        sid = _safe(body.get("sid", "").strip(), "sid")

        label = _safe(body.get("label", "").strip(), "label")

        filename = body.get("filename", "").strip()

        filename = _safe(filename, "filename")

        account_name = os.environ["STORAGE_ACCOUNT_NAME"]

        container = os.environ.get("UPLOADS_CONTAINER", "uploads")

        ttl_min = int(os.environ.get("SAS_TTL_MINUTES", "10"))

        # Preserve extension from filename; default to .pdf if missing.

        _, ext = os.path.splitext(filename)

        ext = ext if ext else ".pdf"

        # Blob naming convention consistent with your pipeline

        # uploads/{sid}_{label}.pdf -> evidence_extract -> evidence/{sid}_{label}.txt

        blob_name = f"{sid}_{label}{ext}"

        # Managed Identity auth

        cred = DefaultAzureCredential()

        svc = BlobServiceClient(

            account_url=f"https://{account_name}.blob.core.windows.net",

            credential=cred

        )

        # User delegation key for MI-based SAS

        start = datetime.now(timezone.utc) - timedelta(minutes=1)

        expiry = datetime.now(timezone.utc) + timedelta(minutes=ttl_min)

        udk = svc.get_user_delegation_key(key_start_time=start, key_expiry_time=expiry)

        sas = generate_blob_sas(

            account_name=account_name,

            container_name=container,

            blob_name=blob_name,

            user_delegation_key=udk,

            permission=BlobSasPermissions(write=True, create=True, add=True),

            expiry=expiry,

            start=start,

            content_type=None

        )

        upload_url = f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas}"

        return func.HttpResponse(

            json.dumps({

                "uploadUrl": upload_url,

                "blobName": blob_name,

                "expiresInMinutes": ttl_min

            }),

            status_code=200,

            mimetype="application/json"

        )

    except ValueError as ve:

        return func.HttpResponse(str(ve), status_code=400)

    except Exception as e:

        logging.exception("issue_sas failed")

        return func.HttpResponse(

            json.dumps({"error": type(e).__name__, "detail": str(e)}),

            status_code=500,

            mimetype="application/json"

        )

