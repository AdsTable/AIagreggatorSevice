from fastapi.routing import APIRoute

@app.on_event("startup")
async def enhanced_startup():
    """Enhanced startup sequence with comprehensive initialization and validation."""
    import time
    startup_start = time.time()
    logger.info(f"🚀 Enhanced startup sequence initiated for {config.app_name} v{config.version}")

    try:
        # Validate critical environment
        await _validate_startup_environment()
        
        # Initialize core systems
        logger.info("🔧 Initializing core systems...")
        await resources.initialize_redis()
        await resources.initialize_ai_client()
        
        # Start background tasks
        logger.info("📋 Starting background task manager...")
        await background_manager.start_background_tasks()
        
        # Perform startup health check
        logger.info("🏥 Performing startup health check...")
        health_status = await resources.health_check()
        
        if health_status.get("status") not in ["healthy", "degraded"]:
            logger.warning("⚠️ System health check indicates issues - review logs")
        
        # Mark initialization as complete
        resources.initialization_complete = True
        startup_duration = time.time() - startup_start

        # Log all registered routes
        logger.info("🔎 Registered API routes:")
        for route in app.routes:
            if isinstance(route, APIRoute):
                logger.info(f"   ✅ {route.path} - {route.methods}")

        # Final startup summary
        logger.info(
            f"✅ Startup completed successfully in {startup_duration:.2f} seconds\n"
            f"   🌐 Server: http://{config.host}:{config.port}\n"
            f"   📚 Docs: {'http://' + config.host + ':' + str(config.port) + '/docs' if config.enable_docs else 'Disabled'}\n"
            f"   📊 Metrics: {'http://' + config.host + ':' + str(config.port) + '/metrics' if config.enable_metrics else 'Disabled'}\n"
            f"   🏥 Health: http://{config.host}:{config.port}/health\n"
            f"   🔧 Providers: {len(provider_registry.list_providers())} registered\n"
            f"   💾 Cache: {'Enabled' if config.enable_cache else 'Disabled'}\n"
            f"   📈 Background tasks: {len(background_manager.tasks)} active"
        )

    except Exception as e:
        logger.critical(f"💥 Startup failed: {e}")
        raise