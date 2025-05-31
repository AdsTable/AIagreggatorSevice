from product_schema import Product
from models import StandardizedProduct

def product_to_standardized(p: Product) -> StandardizedProduct:
    """
    Converts an external Product (from API or import) to the internal StandardizedProduct.
    Only fields present in both models will be mapped. All missing or incompatible fields are set to None.
    """
    raw_data = p.raw_data.root if hasattr(p.raw_data, "__root__") else {}
    return StandardizedProduct(
        category=p.category,
        source_url=str(p.source_url),
        provider_name=p.provider_name,
        product_id=p.product_id,
        name=p.name,
        description=p.description,
        contract_duration_months=p.contract_duration_months,
        available=p.available,
        price_kwh=p.price_kwh,
        standing_charge=p.standing_charge,
        contract_type=p.contract_type,
        monthly_cost=p.monthly_cost,
        data_gb=p.data_gb,
        calls=p.calls,
        texts=p.texts,
        network_type=p.network_type,
        download_speed=p.download_speed,
        upload_speed=p.upload_speed,
        connection_type=p.connection_type,
        data_cap_gb=p.data_cap_gb,
        internet_monthly_cost=getattr(p, "internet_monthly_cost", None),
        raw_data=raw_data
    )

def standardized_to_product(sp: StandardizedProduct) -> Product:
    """
    Converts internal StandardizedProduct to external Product for export.
    """
    from product_schema import RawData
    return Product(
        category=sp.category,
        source_url=sp.source_url,
        provider_name=sp.provider_name,
        product_id=sp.product_id,
        name=sp.name,
        description=sp.description,
        contract_duration_months=sp.contract_duration_months,
        available=sp.available,
        price_kwh=sp.price_kwh,
        standing_charge=sp.standing_charge,
        contract_type=sp.contract_type,
        monthly_cost=sp.monthly_cost,
        data_gb=sp.data_gb,
        calls=sp.calls,
        texts=sp.texts,
        network_type=sp.network_type,
        download_speed=sp.download_speed,
        upload_speed=sp.upload_speed,
        connection_type=sp.connection_type,
        data_cap_gb=sp.data_cap_gb,
        internet_monthly_cost=getattr(sp, "internet_monthly_cost", None),
        raw_data=RawData(__root__=sp.raw_data if sp.raw_data else {})
    )
    
from product_schema import Product, RawData
from models import StandardizedProduct

def rawdata_to_dict(raw):
    if raw is None:
        return {}
    if isinstance(raw, RawData):
        return dict(raw.root)
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "root"):
        return dict(raw.root)
    return dict(raw)

def product_to_standardized(product: Product) -> StandardizedProduct:
    # raw_data всегда dict
    return StandardizedProduct(
        category=product.category,
        source_url=str(product.source_url),
        provider_name=product.provider_name,
        product_id=product.product_id,
        name=product.name,
        description=product.description,
        contract_duration_months=product.contract_duration_months,
        available=product.available,
        price_kwh=product.price_kwh,
        standing_charge=product.standing_charge,
        contract_type=product.contract_type,
        monthly_cost=product.monthly_cost,
        data_gb=product.data_gb,
        calls=product.calls,
        texts=product.texts,
        network_type=product.network_type,
        download_speed=product.download_speed,
        upload_speed=product.upload_speed,
        connection_type=product.connection_type,
        data_cap_gb=product.data_cap_gb,
        internet_monthly_cost=product.internet_monthly_cost,
        raw_data=rawdata_to_dict(product.raw_data)
    )

def standardized_to_product(std: StandardizedProduct) -> Product:
    # raw_data всегда RawData(root=dict)
    return Product(
        category=std.category,
        source_url=std.source_url,
        provider_name=std.provider_name,
        product_id=std.product_id,
        name=std.name,
        description=std.description,
        contract_duration_months=std.contract_duration_months,
        available=std.available,
        price_kwh=std.price_kwh,
        standing_charge=std.standing_charge,
        contract_type=std.contract_type,
        monthly_cost=std.monthly_cost,
        data_gb=std.data_gb,
        calls=std.calls,
        texts=std.texts,
        network_type=std.network_type,
        download_speed=std.download_speed,
        upload_speed=std.upload_speed,
        connection_type=std.connection_type,
        data_cap_gb=std.data_cap_gb,
        internet_monthly_cost=std.internet_monthly_cost,
        raw_data=RawData(root=std.raw_data if std.raw_data is not None else {})
    )