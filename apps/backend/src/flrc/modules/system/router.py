from fastapi import APIRouter, Response

router = APIRouter(tags=["system"])


@router.get("/healthz", status_code=204, response_class=Response)
def healthz() -> Response:
    # This is the only intentionally public non-OAuth response. It carries no
    # environment, dependency, version, host, or school information.
    return Response(status_code=204)
