"""Custom DRF exception handler for consistent error shapes."""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        # Normalize to always have a `detail` key or `errors` key
        if isinstance(response.data, dict) and "detail" not in response.data:
            response.data = {"errors": response.data}
        return response

    # Unhandled exceptions → 500
    return Response(
        {"detail": "An unexpected server error occurred."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
