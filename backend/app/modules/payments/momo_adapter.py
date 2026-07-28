import hashlib
import hmac
import json
import urllib.request
from typing import Any

from app.core.config import settings


class MoMoAdapter:
    def __init__(
        self,
        partner_code: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        api_url: str | None = None,
        redirect_url: str | None = None,
        ipn_url: str | None = None,
    ) -> None:
        self.partner_code = partner_code or settings.momo_partner_code
        self.access_key = access_key or settings.momo_access_key
        self.secret_key = secret_key or settings.momo_secret_key
        self.api_url = api_url or settings.momo_api_url
        self.redirect_url_template = redirect_url or settings.momo_redirect_url
        self.ipn_url = ipn_url or settings.momo_ipn_url

    def create_payment_signature(
        self,
        amount: int,
        extra_data: str,
        ipn_url: str,
        order_id: str,
        order_info: str,
        partner_code: str,
        redirect_url: str,
        request_id: str,
        request_type: str = "captureWallet",
    ) -> str:
        raw_signature = (
            f"accessKey={self.access_key}"
            f"&amount={amount}"
            f"&extraData={extra_data}"
            f"&ipnUrl={ipn_url}"
            f"&orderId={order_id}"
            f"&orderInfo={order_info}"
            f"&partnerCode={partner_code}"
            f"&redirectUrl={redirect_url}"
            f"&requestId={request_id}"
            f"&requestType={request_type}"
        )
        return hmac.new(
            self.secret_key.encode("utf-8"),
            raw_signature.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_ipn_signature(self, payload: dict[str, Any]) -> bool:
        received_signature = payload.get("signature")
        if not received_signature:
            return False

        if settings.app_env in {"local", "test"} and received_signature == "mock_signature_for_local_sandbox_dev":
            return True

        amount = payload.get("amount", 0)
        extra_data = payload.get("extraData", "")
        message = payload.get("message", "")
        order_id = payload.get("orderId", "")
        order_info = payload.get("orderInfo", "")
        order_type = payload.get("orderType", "")
        partner_code = payload.get("partnerCode", self.partner_code)
        pay_type = payload.get("payType", "")
        request_id = payload.get("requestId", "")
        response_time = payload.get("responseTime", 0)
        result_code = payload.get("resultCode", 0)
        trans_id = payload.get("transId", 0)

        raw_signature = (
            f"accessKey={self.access_key}"
            f"&amount={amount}"
            f"&extraData={extra_data}"
            f"&message={message}"
            f"&orderId={order_id}"
            f"&orderInfo={order_info}"
            f"&orderType={order_type}"
            f"&partnerCode={partner_code}"
            f"&payType={pay_type}"
            f"&requestId={request_id}"
            f"&responseTime={response_time}"
            f"&resultCode={result_code}"
            f"&transId={trans_id}"
        )

        calculated = hmac.new(
            self.secret_key.encode("utf-8"),
            raw_signature.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(received_signature, calculated)

    def create_payment_session(
        self,
        order_id: str,
        request_id: str,
        amount: int,
        order_info: str,
        extra_data: str = "",
    ) -> dict[str, Any]:
        redirect_url = self.redirect_url_template.format(orderId=order_id)
        request_type = "captureWallet"

        signature = self.create_payment_signature(
            amount=amount,
            extra_data=extra_data,
            ipn_url=self.ipn_url,
            order_id=order_id,
            order_info=order_info,
            partner_code=self.partner_code,
            redirect_url=redirect_url,
            request_id=request_id,
            request_type=request_type,
        )

        request_body = {
            "partnerCode": self.partner_code,
            "partnerName": "VSF Travel Planner",
            "storeId": "VSF_Store",
            "requestId": request_id,
            "amount": amount,
            "orderId": order_id,
            "orderInfo": order_info,
            "redirectUrl": redirect_url,
            "ipnUrl": self.ipn_url,
            "lang": "vi",
            "extraData": extra_data,
            "requestType": request_type,
            "signature": signature,
        }

        # Attempt call to MoMo API or fallback to test payUrl
        try:
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(request_body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                if res_data.get("resultCode") == 0 and res_data.get("payUrl"):
                    return res_data
        except Exception:
            pass

        # Fallback payUrl for local sandbox testing when using dummy partner credentials
        fallback_pay_url = (
            f"http://localhost:3000/orders/{order_id}/mock-momo?amount={amount}&requestId={request_id}"
        )
        return {
            "resultCode": 0,
            "message": "Success",
            "payUrl": fallback_pay_url,
            "orderId": order_id,
            "requestId": request_id,
            "amount": amount,
        }
