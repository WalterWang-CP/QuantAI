import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import (
    and_,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.identity import (
    Company,
    Listing,
    Security,
)
from app.db.models.identity_resolution import (
    CompanyAlias,
    CompanyIdentifier,
    CompanyRelationship,
    ListingLifecycleEvent,
    ListingProviderSymbol,
    SecurityIdentifier,
)
from app.identity.resolution_schemas import (
    CompanyAliasCreate,
    CompanyIdentifierCreate,
    CompanyRelationshipCreate,
    ListingLifecycleEventCreate,
    ListingProviderSymbolCreate,
    SecurityIdentifierCreate,
)


IDENTITY_EVENT_PROVIDER = "manual"
IDENTITY_EVENT_DATASET = "IDENTITY_EVENTS"

@dataclass(frozen=True)
class ProviderSymbolSegment:
    start_date: date
    end_date: date
    symbol: str

def valid_as_of(
    model,
    as_of_date: date,
):
    return and_(
        or_(
            model.valid_from.is_(None),
            model.valid_from
            <= as_of_date,
        ),
        or_(
            model.valid_to.is_(None),
            model.valid_to
            >= as_of_date,
        ),
    )

def add_company_identifier(
    database: Session,
    payload: CompanyIdentifierCreate,
) -> CompanyIdentifier:
    company = database.get(
        Company,
        payload.company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    statement = select(
        CompanyIdentifier
    ).where(
        CompanyIdentifier.company_id
        == payload.company_id,

        CompanyIdentifier.scheme
        == payload.scheme,

        CompanyIdentifier.value
        == payload.value,

        CompanyIdentifier.valid_from
        == payload.valid_from,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.valid_to = (
            payload.valid_to
        )

        existing.is_primary = (
            payload.is_primary
        )

        database.commit()
        database.refresh(existing)

        return existing

    identifier = CompanyIdentifier(
        company_id=
            payload.company_id,

        scheme=
            payload.scheme,

        value=
            payload.value,

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,

        is_primary=
            payload.is_primary,
    )

    database.add(identifier)
    database.commit()
    database.refresh(identifier)

    return identifier


def get_company_identifiers(
    database: Session,
    company_id: uuid.UUID,
) -> list[CompanyIdentifier]:
    company = database.get(
        Company,
        company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    statement = (
        select(
            CompanyIdentifier
        )
        .where(
            CompanyIdentifier.company_id
            == company_id
        )
        .order_by(
            CompanyIdentifier.scheme,
            CompanyIdentifier.valid_from,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )


def resolve_company_identifier(
    database: Session,
    scheme: str,
    value: str,
    as_of_date: date | None = None,
) -> Company:
    scheme = (
        scheme
        .strip()
        .upper()
    )

    value = value.strip()

    statement = (
        select(Company)
        .join(
            CompanyIdentifier,
            CompanyIdentifier.company_id
            == Company.id,
        )
        .where(
            CompanyIdentifier.scheme
            == scheme,

            CompanyIdentifier.value
            == value,
        )
    )

    if as_of_date is not None:
        statement = statement.where(
            valid_as_of(
                CompanyIdentifier,
                as_of_date,
            )
        )

    company = database.scalar(
        statement
    )

    if company is None:
        raise LookupError(
            "No company matches that "
            "identifier."
        )

    return company

def add_security_identifier(
    database: Session,
    payload: SecurityIdentifierCreate,
) -> SecurityIdentifier:
    security = database.get(
        Security,
        payload.security_id,
    )

    if security is None:
        raise LookupError(
            "Security does not exist."
        )

    statement = select(
        SecurityIdentifier
    ).where(
        SecurityIdentifier.security_id
        == payload.security_id,

        SecurityIdentifier.scheme
        == payload.scheme,

        SecurityIdentifier.value
        == payload.value,

        SecurityIdentifier.valid_from
        == payload.valid_from,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.valid_to = (
            payload.valid_to
        )

        existing.is_primary = (
            payload.is_primary
        )

        database.commit()
        database.refresh(existing)

        return existing

    identifier = SecurityIdentifier(
        security_id=
            payload.security_id,

        scheme=
            payload.scheme,

        value=
            payload.value,

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,

        is_primary=
            payload.is_primary,
    )

    database.add(identifier)
    database.commit()
    database.refresh(identifier)

    return identifier

def resolve_security_identifier(
    database: Session,
    scheme: str,
    value: str,
    as_of_date: date | None = None,
) -> Security:
    scheme = (
        scheme
        .strip()
        .upper()
    )

    value = value.strip()

    statement = (
        select(Security)
        .join(
            SecurityIdentifier,
            SecurityIdentifier.security_id
            == Security.id,
        )
        .where(
            SecurityIdentifier.scheme
            == scheme,

            SecurityIdentifier.value
            == value,
        )
    )

    if as_of_date is not None:
        statement = statement.where(
            valid_as_of(
                SecurityIdentifier,
                as_of_date,
            )
        )

    security = database.scalar(
        statement
    )

    if security is None:
        raise LookupError(
            "No security matches that "
            "identifier."
        )

    return security

def add_company_alias(
    database: Session,
    payload: CompanyAliasCreate,
) -> CompanyAlias:
    company = database.get(
        Company,
        payload.company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    alias = CompanyAlias(
        company_id=
            payload.company_id,

        alias=
            payload.alias.strip(),

        alias_type=
            payload.alias_type.strip(),

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,
    )

    database.add(alias)
    database.commit()
    database.refresh(alias)

    return alias


def get_company_aliases(
    database: Session,
    company_id: uuid.UUID,
) -> list[CompanyAlias]:
    statement = (
        select(CompanyAlias)
        .where(
            CompanyAlias.company_id
            == company_id
        )
        .order_by(
            CompanyAlias.alias
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

def add_listing_provider_symbol(
    database: Session,
    payload:
        ListingProviderSymbolCreate,
) -> ListingProviderSymbol:
    listing = database.get(
        Listing,
        payload.listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    statement = select(
        ListingProviderSymbol
    ).where(
        ListingProviderSymbol.listing_id
        == payload.listing_id,

        ListingProviderSymbol.provider_name
        == payload.provider_name,

        ListingProviderSymbol.symbol
        == payload.symbol,

        ListingProviderSymbol.valid_from
        == payload.valid_from,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.valid_to = (
            payload.valid_to
        )

        database.commit()
        database.refresh(existing)

        return existing

    symbol = ListingProviderSymbol(
        listing_id=
            payload.listing_id,

        provider_name=
            payload.provider_name,

        symbol=
            payload.symbol,

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,
    )

    database.add(symbol)
    database.commit()
    database.refresh(symbol)

    return symbol

def _select_active_provider_symbol(
    mappings: list[
        ListingProviderSymbol
    ],
    as_of_date: date,
) -> ListingProviderSymbol | None:
    active = []

    for mapping in mappings:
        if (
            mapping.valid_from is not None
            and mapping.valid_from
            > as_of_date
        ):
            continue

        if (
            mapping.valid_to is not None
            and mapping.valid_to
            < as_of_date
        ):
            continue

        active.append(
            mapping
        )

    if not active:
        return None

    latest_start = max(
        (
            mapping.valid_from
            or date.min
        )
        for mapping in active
    )

    preferred = [
        mapping
        for mapping in active
        if (
            mapping.valid_from
            or date.min
        )
        == latest_start
    ]

    symbols = {
        mapping.symbol
        for mapping in preferred
    }

    if len(symbols) > 1:
        raise ValueError(
            "Ambiguous provider-symbol "
            "mapping: multiple active "
            "symbols have the same "
            "valid_from date."
        )

    preferred.sort(
        key=lambda mapping:
            str(mapping.id)
    )

    return preferred[0]

def resolve_provider_symbol(
    database: Session,
    listing_id: uuid.UUID,
    provider_name: str,
    as_of_date: date | None = None,
) -> str:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    provider_name = (
        provider_name
        .strip()
        .lower()
    )

    if as_of_date is None:
        as_of_date = date.today()

    mappings = list(
        database.scalars(
            select(
                ListingProviderSymbol
            )
            .where(
                ListingProviderSymbol
                .listing_id
                == listing_id,

                ListingProviderSymbol
                .provider_name
                == provider_name,

                or_(
                    ListingProviderSymbol
                    .valid_from
                    .is_(None),

                    ListingProviderSymbol
                    .valid_from
                    <= as_of_date,
                ),

                or_(
                    ListingProviderSymbol
                    .valid_to
                    .is_(None),

                    ListingProviderSymbol
                    .valid_to
                    >= as_of_date,
                ),
            )
        ).all()
    )

    mapping = (
        _select_active_provider_symbol(
            mappings=mappings,
            as_of_date=as_of_date,
        )
    )

    if mapping is not None:
        return mapping.symbol

    return listing.ticker


def get_company_relationships(
    database: Session,
    company_id: uuid.UUID,
) -> list[CompanyRelationship]:
    company = database.get(
        Company,
        company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    statement = (
        select(
            CompanyRelationship
        )
        .where(
            or_(
                CompanyRelationship
                .source_company_id
                == company_id,

                CompanyRelationship
                .target_company_id
                == company_id,
            )
        )
        .order_by(
            CompanyRelationship
            .effective_date,
            CompanyRelationship.id,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

def add_listing_lifecycle_event(
    database: Session,
    payload: ListingLifecycleEventCreate,
) -> ListingLifecycleEvent:
    from app.market_data.service import (
    get_or_create_data_source,
    )
    listing = database.get(
        Listing,
        payload.listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    allowed_events = {
        "ticker_change",
        "exchange_change",
        "delisting",
        "relisting",
    }

    if (
        payload.event_type
        not in allowed_events
    ):
        raise ValueError(
            "Unsupported listing "
            "lifecycle event type."
        )

    successor = None

    if (
        payload.successor_listing_id
        is not None
    ):
        successor = database.get(
            Listing,
            payload.successor_listing_id,
        )

        if successor is None:
            raise LookupError(
                "Successor listing "
                "does not exist."
            )

    transition_types = {
        "ticker_change",
        "exchange_change",
        "relisting",
    }

    if (
        payload.event_type
        in transition_types
    ):
        if successor is None:
            raise ValueError(
                "This lifecycle transition "
                "requires a successor listing."
            )

        if (
            successor.security_id
            != listing.security_id
        ):
            raise ValueError(
                "Ticker/exchange/relisting "
                "transitions must remain "
                "attached to the same "
                "security."
            )

    source = get_or_create_data_source(
        database=database,

        provider_name=
            IDENTITY_EVENT_PROVIDER,

        dataset_name=
            IDENTITY_EVENT_DATASET,
    )

    statement = select(
        ListingLifecycleEvent
    ).where(
        ListingLifecycleEvent.listing_id
        == listing.id,

        ListingLifecycleEvent.source_id
        == source.id,

        ListingLifecycleEvent.event_type
        == payload.event_type,

        ListingLifecycleEvent.effective_date
        == payload.effective_date,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.successor_listing_id = (
            payload.successor_listing_id
        )

        existing.known_date = (
            payload.known_date
        )

        existing.note = (
            payload.note
        )

        database.commit()
        database.refresh(existing)

        return existing

    event = ListingLifecycleEvent(
        listing_id=
            listing.id,

        successor_listing_id=
            payload.successor_listing_id,

        source_id=
            source.id,

        event_type=
            payload.event_type,

        effective_date=
            payload.effective_date,

        known_date=
            payload.known_date,

        note=
            payload.note,
    )

    database.add(event)
    database.commit()
    database.refresh(event)

    return event

def get_listing_lifecycle_events(
    database: Session,
    listing_id: uuid.UUID,
) -> list[ListingLifecycleEvent]:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    statement = (
        select(
            ListingLifecycleEvent
        )
        .where(
            or_(
                ListingLifecycleEvent.listing_id
                == listing_id,

                ListingLifecycleEvent.successor_listing_id
                == listing_id,
            )
        )
        .order_by(
            ListingLifecycleEvent.effective_date,
            ListingLifecycleEvent.id,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

def get_provider_symbol_segments(
    database: Session,
    listing_id: uuid.UUID,
    provider_name: str,
    start_date: date,
    end_date: date,
) -> list[ProviderSymbolSegment]:
    if end_date < start_date:
        raise ValueError(
            "end_date cannot be earlier "
            "than start_date."
        )

    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    provider_name = (
        provider_name
        .strip()
        .lower()
    )

    mappings = list(
        database.scalars(
            select(
                ListingProviderSymbol
            )
            .where(
                ListingProviderSymbol
                .listing_id
                == listing_id,

                ListingProviderSymbol
                .provider_name
                == provider_name,

                or_(
                    ListingProviderSymbol
                    .valid_from
                    .is_(None),

                    ListingProviderSymbol
                    .valid_from
                    <= end_date,
                ),

                or_(
                    ListingProviderSymbol
                    .valid_to
                    .is_(None),

                    ListingProviderSymbol
                    .valid_to
                    >= start_date,
                ),
            )
        ).all()
    )

    boundaries = {
        start_date,
    }

    for mapping in mappings:
        if (
            mapping.valid_from is not None
            and start_date
            < mapping.valid_from
            <= end_date
        ):
            boundaries.add(
                mapping.valid_from
            )

        if (
            mapping.valid_to is not None
            and start_date
            <= mapping.valid_to
            < end_date
        ):
            boundaries.add(
                mapping.valid_to
                + timedelta(days=1)
            )

    ordered_boundaries = sorted(
        boundaries
    )

    segments = []

    for index, segment_start in enumerate(
        ordered_boundaries
    ):
        if (
            index + 1
            < len(
                ordered_boundaries
            )
        ):
            segment_end = (
                ordered_boundaries[
                    index + 1
                ]
                - timedelta(days=1)
            )

        else:
            segment_end = end_date

        active_mapping = (
            _select_active_provider_symbol(
                mappings=mappings,
                as_of_date=
                    segment_start,
            )
        )

        if active_mapping is None:
            symbol = listing.ticker

        else:
            symbol = (
                active_mapping.symbol
            )

        if (
            segments
            and segments[-1].symbol
            == symbol
            and (
                segments[-1].end_date
                + timedelta(days=1)
            )
            == segment_start
        ):
            previous = segments[-1]

            segments[-1] = (
                ProviderSymbolSegment(
                    start_date=
                        previous.start_date,

                    end_date=
                        segment_end,

                    symbol=
                        previous.symbol,
                )
            )

        else:
            segments.append(
                ProviderSymbolSegment(
                    start_date=
                        segment_start,

                    end_date=
                        segment_end,

                    symbol=symbol,
                )
            )

    return segments

def get_company_primary_listings(
    database: Session,
    company_id: uuid.UUID,
    as_of_date: date,
) -> list[Listing]:
    company = database.get(
        Company,
        company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    statement = (
        select(
            Listing
        )
        .join(
            Security,
            Listing.security_id
            == Security.id,
        )
        .where(
            Security.company_id
            == company_id,

            Listing.is_primary
            .is_(True),

            Listing.start_date
            <= as_of_date,
        )
        .order_by(
            Listing.start_date,
            Listing.id,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

def add_company_relationship(
    database: Session,
    payload: CompanyRelationshipCreate,
) -> CompanyRelationship:
    from app.market_data.service import (
        get_or_create_data_source,
    )

    source_company = database.get(
        Company,
        payload.source_company_id,
    )

    if source_company is None:
        raise LookupError(
            "Source company does not exist."
        )

    target_company = database.get(
        Company,
        payload.target_company_id,
    )

    if target_company is None:
        raise LookupError(
            "Target company does not exist."
        )

    if (
        payload.source_company_id
        == payload.target_company_id
    ):
        raise ValueError(
            "A company cannot have a "
            "lifecycle relationship "
            "with itself."
        )

    allowed_relationships = {
        "merged_into",
        "acquired_by",
        "spun_off_into",
        "successor_of",
    }

    if (
        payload.relationship_type
        not in allowed_relationships
    ):
        raise ValueError(
            "Unsupported company "
            "relationship type."
        )

    source = get_or_create_data_source(
        database=database,
        provider_name=
            IDENTITY_EVENT_PROVIDER,
        dataset_name=
            IDENTITY_EVENT_DATASET,
    )

    statement = select(
        CompanyRelationship
    ).where(
        CompanyRelationship
        .source_company_id
        == payload.source_company_id,

        CompanyRelationship
        .target_company_id
        == payload.target_company_id,

        CompanyRelationship
        .source_id
        == source.id,

        CompanyRelationship
        .relationship_type
        == payload.relationship_type,

        CompanyRelationship
        .effective_date
        == payload.effective_date,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.known_date = (
            payload.known_date
        )

        existing.note = (
            payload.note
        )

        database.commit()
        database.refresh(existing)

        return existing

    relationship = CompanyRelationship(
        source_company_id=
            payload.source_company_id,

        target_company_id=
            payload.target_company_id,

        source_id=
            source.id,

        relationship_type=
            payload.relationship_type,

        effective_date=
            payload.effective_date,

        known_date=
            payload.known_date,

        note=
            payload.note,
    )

    database.add(
        relationship
    )

    database.commit()
    database.refresh(
        relationship
    )

    return relationship
def add_company_relationship(
    database: Session,
    payload: CompanyRelationshipCreate,
) -> CompanyRelationship:
    from app.market_data.service import (
        get_or_create_data_source,
    )

    source_company = database.get(
        Company,
        payload.source_company_id,
    )

    if source_company is None:
        raise LookupError(
            "Source company does not exist."
        )

    target_company = database.get(
        Company,
        payload.target_company_id,
    )

    if target_company is None:
        raise LookupError(
            "Target company does not exist."
        )

    if (
        payload.source_company_id
        == payload.target_company_id
    ):
        raise ValueError(
            "A company cannot have a "
            "lifecycle relationship "
            "with itself."
        )

    allowed_relationships = {
        "merged_into",
        "acquired_by",
        "spun_off_into",
        "successor_of",
    }

    if (
        payload.relationship_type
        not in allowed_relationships
    ):
        raise ValueError(
            "Unsupported company "
            "relationship type."
        )

    source = get_or_create_data_source(
        database=database,
        provider_name=
            IDENTITY_EVENT_PROVIDER,
        dataset_name=
            IDENTITY_EVENT_DATASET,
    )

    statement = select(
        CompanyRelationship
    ).where(
        CompanyRelationship
        .source_company_id
        == payload.source_company_id,

        CompanyRelationship
        .target_company_id
        == payload.target_company_id,

        CompanyRelationship
        .source_id
        == source.id,

        CompanyRelationship
        .relationship_type
        == payload.relationship_type,

        CompanyRelationship
        .effective_date
        == payload.effective_date,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.known_date = (
            payload.known_date
        )

        existing.note = (
            payload.note
        )

        database.commit()
        database.refresh(existing)

        return existing

    relationship = CompanyRelationship(
        source_company_id=
            payload.source_company_id,

        target_company_id=
            payload.target_company_id,

        source_id=
            source.id,

        relationship_type=
            payload.relationship_type,

        effective_date=
            payload.effective_date,

        known_date=
            payload.known_date,

        note=
            payload.note,
    )

    database.add(
        relationship
    )

    database.commit()
    database.refresh(
        relationship
    )

    return relationship