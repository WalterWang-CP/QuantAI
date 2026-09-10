from fastapi import (
    APIRouter,
    HTTPException,
)

from app.providers.alpha_vantage import (
    AlphaVantageProvider,
)
from app.providers.schemas import (
    MarketBarRead,
    MarketDataPreview,
)
import httpx


router = APIRouter(
    prefix="/providers",
    tags=["Providers"],
)


@router.get(
    "/alpha-vantage/daily/{symbol}",
    response_model=MarketDataPreview,
)
def preview_alpha_vantage_daily_prices(
    symbol: str,
    full_history: bool = False,
):
    provider = AlphaVantageProvider()

    try:
        bars = provider.get_daily_prices(
            symbol=symbol,
            full_history=full_history,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Unable to communicate with Alpha Vantage.",
        )

    sample_bars = bars[-10:]

    sample = [
        MarketBarRead(
            trading_date=bar.trading_date,
            open_price=bar.open_price,
            high_price=bar.high_price,
            low_price=bar.low_price,
            close_price=bar.close_price,
            volume=bar.volume,
        )
        for bar in sample_bars
    ]

    return MarketDataPreview(
        provider=provider.provider_name,
        symbol=symbol.upper(),
        full_history_requested=full_history,
        bar_count=len(bars),
        first_date=(
            bars[0].trading_date
            if bars
            else None
        ),
        last_date=(
            bars[-1].trading_date
            if bars
            else None
        ),
        sample=sample,
    )