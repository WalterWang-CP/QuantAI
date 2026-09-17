class ProviderError(RuntimeError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTemporaryError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


class ProviderCapabilityError(
    ProviderRequestError
):
    pass