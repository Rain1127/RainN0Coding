from fastapi import FastAPI


def register_routes(
    app: FastAPI,
    *,
    generate_code_handler,
    route_code_gen_type_handler,
    health_handler,
    execution_status_handler,
) -> None:
    app.post("/api/generate-code")(generate_code_handler)
    app.post("/api/route-codegen-type")(route_code_gen_type_handler)
    app.get("/api/health")(health_handler)
    app.get("/api/execution-status/{app_id}")(execution_status_handler)
