#!/usr/bin/env python3
"""
Paperless Factory CLI
Provides the command-line interface for the Paperless Factory workflow.
"""

import argparse
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import get_settings
from app.database import init_db
from app.services.folder_setup import setup_folders, select_root_folder
from loguru import logger


def init_system():
    """Initialize the Paperless Factory application."""
    print("🚀 Initializing Paperless Factory...")
    
    # Initialize database first (create tables)
    print("🗄️  Initializing database...")
    init_db()
    
    # Setup folders (requires database to be initialized)
    print("📁 Setting up folder structure...")
    from app.database import SessionLocal
    with SessionLocal() as db:
        setup_folders(db)
    
    print("✅ System initialized successfully!")
    print("\nNext steps:")
    print("1. Run 'python cli.py serve' to start the web server")
    print("2. Navigate to http://localhost:8000")
    print("3. Configure your AI provider in the Settings tab")
    print("4. Start uploading documents")


def serve():
    """Start the web server"""
    import uvicorn
    from app.database import SessionLocal
    
    # The settings query below needs the settings table to exist on first run.
    init_db()

    with SessionLocal() as db:
        settings = get_settings(db)
    
    print("🌐 Starting Paperless Factory...")
    print(f"📁 Staging folder: {settings.staging_folder}")
    print(f"💾 Data folder: {settings.data_folder}")
    print(f"📄 Storage folder: {settings.storage_folder}")
    host = os.getenv("DOCUMENT_MANAGER_HOST", "127.0.0.1")
    print("\n🔗 Access the system at: http://localhost:8000")
    print("📚 API documentation at: http://localhost:8000/docs")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=8000,
        reload=True,
        log_level="info"
    )


def status():
    """Show system status"""
    from app.database import SessionLocal
    with SessionLocal() as db:
        settings = get_settings(db)
    
    print("📊 Paperless Factory Status")
    print("=" * 40)
    
    # Check folders
    folders = [
        ("Staging", settings.staging_folder),
        ("Data", settings.data_folder),
        ("Storage", settings.storage_folder),
        ("Logs", settings.logs_folder)
    ]
    
    for name, path in folders:
        folder_path = Path(path)
        exists = folder_path.exists()
        file_count = len(list(folder_path.glob("*"))) if exists else 0
        
        status_icon = "✅" if exists else "❌"
        print(f"{status_icon} {name}: {path} ({file_count} files)")
    
    # Check database
    try:
        from app.database import SessionLocal
        from app.models import Document

        with SessionLocal() as db:
            doc_count = db.query(Document).count()
            pending_ai = db.query(Document).filter(Document.ai_status == "pending").count()

        print(f"\n📄 Documents: {doc_count} total")
        print(f"🤖 Pending AI: {pending_ai}")

    except Exception as e:
        print(f"❌ Database error: {e}")
    
    # Check AI configuration
    print(f"\n🤖 AI Provider: {settings.ai_provider.upper()}")
    print(f"   Chat model:     {AIClientFactory.get_chat_model(settings)}")
    print(f"   Analysis model: {AIClientFactory.get_analysis_model(settings)}")
    print(f"   Vision model:   {AIClientFactory.get_vision_model(settings)}")
    print(f"   Reasoning:      {settings.reasoning_effort}")

    config_status = AIClientFactory.validate_configuration(settings)
    if config_status['valid']:
        print(f"✅ {settings.ai_provider.upper()} API: Configured")
    else:
        print(f"❌ {settings.ai_provider.upper()} API: Not configured")
        for error in config_status['errors']:
            print(f"   - {error}")

    if config_status['warnings']:
        print("⚠️  Warnings:")
        for warning in config_status['warnings']:
            print(f"   - {warning}")

    # Embeddings
    from app.services.embedding_service import EmbeddingService

    embed_info = EmbeddingService(settings).describe()
    icon = "✅" if embed_info["ready"] else "⚠️ "
    print(f"\n🔢 Embeddings: {embed_info['provider']} / {embed_info['model']}")
    print(f"{icon} Ready: {embed_info['ready']} (dimensions: {embed_info['dimensions']})")


def list_users():
    """Show the accounts that exist."""
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        users = db.query(User).order_by(User.created_at).all()

    if not users:
        print("No users yet. Open http://localhost:8000 to create the first admin.")
        return

    print(f"{len(users)} user(s):")
    for user in users:
        flags = []
        if user.is_admin:
            flags.append("admin")
        if not user.is_active:
            flags.append("INACTIVE")
        if user.must_change_password:
            flags.append("must-change-password")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        last = user.last_login.isoformat(" ", "seconds") if user.last_login else "never"
        print(f"  {user.username:20s} {user.email:32s} last login: {last}{suffix}")


def reset_password(username: str, password: str = None):
    """Set a new password for an account (local recovery)."""
    import getpass

    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = db.query(User).filter(User.email == username).first()
        if not user:
            print(f"❌ No user named '{username}'. Run 'python cli.py users' to list them.")
            return 1

        if not password:
            try:
                password = getpass.getpass(f"New password for {user.username}: ")
                confirm = getpass.getpass("Confirm: ")
            except Exception:
                print("❌ Cannot prompt here. Use: cli.py reset-password NAME --password SECRET")
                return 1
            if password != confirm:
                print("❌ Passwords do not match")
                return 1

        if len(password) < 8:
            print("❌ Password must be at least 8 characters")
            return 1

        user.set_password(password)
        user.must_change_password = False
        user.is_active = True
        db.commit()

    print(f"✅ Password updated for '{username}'")
    print("   If you were locked out, restart the server to clear the login throttle.")
    return 0


def sync_model_config():
    """Push config/models.json into the database settings table.

    Database settings override environment variables and file defaults, so an
    existing install keeps using stale model names until they are synced.
    """
    from app.database import SessionLocal
    from app.models import Settings as SettingsModel
    from app.services.model_config import as_settings_overrides, get_config_path
    from app.config import reset_settings

    reset_settings()  # drop caches so the file is re-read
    overrides = as_settings_overrides()

    print(f"📄 Reading {get_config_path()}")

    updated, created = [], []
    with SessionLocal() as db:
        for key, value in overrides.items():
            setting = db.query(SettingsModel).filter(SettingsModel.key == key).first()
            new_value = str(value)
            if setting:
                if setting.value != new_value:
                    print(f"   {key}: {setting.value!r} -> {new_value!r}")
                    setting.value = new_value
                    updated.append(key)
            else:
                db.add(
                    SettingsModel(
                        key=key,
                        value=new_value,
                        description="Synced from config/models.json",
                    )
                )
                created.append(key)
        db.commit()

    reset_settings()

    print(f"\n✅ Synced model configuration: {len(updated)} updated, {len(created)} created")
    if created:
        print(f"   Created: {', '.join(created)}")


def setup_root():
    """Setup root folder interactively"""
    print("📁 Select root folder for Paperless Factory")
    
    root_folder = select_root_folder()
    if root_folder:
        print(f"✅ Root folder selected: {root_folder}")
        
        # Save to database
        from app.database import SessionLocal
        from app.models import Settings as SettingsModel
        
        with SessionLocal() as db:
            setting = db.query(SettingsModel).filter(SettingsModel.key == "root_folder").first()
            if setting:
                setting.value = root_folder
            else:
                setting = SettingsModel(key="root_folder", value=root_folder, description="Root folder for documents")
                db.add(setting)
            db.commit()
        
        print("✅ Root folder saved to database configuration")
    else:
        print("❌ No folder selected")


def handle_db_command(args):
    """Handle database management commands"""
    if not args.db_command:
        print("Please specify a database command. Use 'cli.py db --help' for options.")
        return
    
    from app.database import get_db
    from app.utils.database_optimization import create_indexes, analyze_database, optimize_database, get_database_size
    
    with next(get_db()) as db:
        if args.db_command == "create-indexes":
            print("🔧 Creating database indexes...")
            try:
                results = create_indexes(db)
                
                created_count = sum(1 for r in results if r.get('status') == 'created')
                failed_count = sum(1 for r in results if r.get('status') == 'failed')
                
                print(f"✅ Created {created_count} indexes")
                if failed_count > 0:
                    print(f"❌ Failed to create {failed_count} indexes")
                    for result in results:
                        if result.get('status') == 'failed':
                            print(f"   - {result.get('name', 'unknown')}: {result.get('error')}")
                
            except Exception as e:
                print(f"❌ Error creating indexes: {e}")
        
        elif args.db_command == "analyze":
            print("📊 Analyzing database performance...")
            try:
                analysis = analyze_database(db)
                
                print("\n📈 Table Statistics:")
                for stat in analysis.get('table_stats', []):
                    print(f"   {stat['table']}: {stat['row_count']:,} rows")
                
                print(f"\n🔍 Found {len(analysis.get('index_usage', []))} indexes")
                
                print("\n💡 Recommendations:")
                for rec in analysis.get('recommendations', []):
                    priority_icon = "🔴" if rec['priority'] == 'high' else "🟡" if rec['priority'] == 'medium' else "🟢"
                    print(f"   {priority_icon} {rec['recommendation']}")
                    print(f"      Reason: {rec['reason']}")
                
            except Exception as e:
                print(f"❌ Error analyzing database: {e}")
        
        elif args.db_command == "optimize":
            print("⚡ Optimizing database...")
            try:
                results = optimize_database(db)
                
                if results.get('vacuum'):
                    print("✅ VACUUM completed")
                if results.get('analyze'):
                    print("✅ ANALYZE completed")
                if results.get('reindex'):
                    print("✅ REINDEX completed")
                
                if results.get('errors'):
                    print("❌ Errors during optimization:")
                    for error in results['errors']:
                        print(f"   - {error}")
                
            except Exception as e:
                print(f"❌ Error optimizing database: {e}")
        
        elif args.db_command == "size":
            print("📏 Getting database size information...")
            try:
                size_info = get_database_size()
                
                if 'total_size_mb' in size_info:
                    print(f"\n💾 Total Database Size: {size_info['total_size_mb']} MB")
                
                if 'tables' in size_info:
                    print("\n📊 Table Sizes:")
                    for table, info in size_info['tables'].items():
                        if 'size_mb' in info:
                            print(f"   {table}: {info['size_mb']} MB")
                        elif 'estimated_size_kb' in info:
                            print(f"   {table}: {info['estimated_size_kb']} KB ({info['row_count']} rows)")
                
            except Exception as e:
                print(f"❌ Error getting database size: {e}")


def handle_backup_command(args):
    """Handle backup management commands"""
    if not args.backup_command:
        print("Please specify a backup command. Use 'cli.py backup --help' for options.")
        return
    
    from app.database import get_db
    from app.utils.backup import create_backup, restore_backup, list_backups
    from pathlib import Path
    
    if args.backup_command == "create":
        print("💾 Creating system backup...")
        try:
            with next(get_db()) as db:
                backup_info = create_backup(
                    db_session=db,
                    backup_name=args.name,
                    include_files=not args.no_files
                )
                
                print("✅ Backup created successfully!")
                print(f"   Name: {backup_info['name']}")
                print(f"   Archive: {backup_info.get('archive_path')}")
                print(f"   Size: {backup_info.get('archive_size_mb', 0)} MB")
                
                if backup_info.get('errors'):
                    print("❌ Errors during backup:")
                    for error in backup_info['errors']:
                        print(f"   - {error}")
        
        except Exception as e:
            print(f"❌ Backup failed: {e}")
    
    elif args.backup_command == "restore":
        archive_path = Path(args.archive)
        if not archive_path.exists():
            print(f"❌ Backup archive not found: {archive_path}")
            return
        
        print(f"🔄 Restoring backup from {archive_path}...")
        
        # Confirm restore
        response = input("⚠️  This will overwrite existing data. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Restore cancelled.")
            return
        
        try:
            with next(get_db()) as db:
                restore_info = restore_backup(
                    archive_path=archive_path,
                    db_session=db,
                    restore_files=not args.no_files
                )
                
                print("✅ Restore completed successfully!")
                if restore_info.get('database_restored'):
                    print("   ✅ Database restored")
                if restore_info.get('files_restored'):
                    print("   ✅ Files restored")
                
                if restore_info.get('errors'):
                    print("❌ Errors during restore:")
                    for error in restore_info['errors']:
                        print(f"   - {error}")
        
        except Exception as e:
            print(f"❌ Restore failed: {e}")
    
    elif args.backup_command == "list":
        print("📋 Available backups:")
        try:
            backups = list_backups()
            
            if not backups:
                print("   No backups found.")
                return
            
            for backup in backups:
                print(f"\n📦 {backup['filename']}")
                print(f"   Size: {backup['size_mb']} MB")
                if backup.get('created_at'):
                    print(f"   Created: {backup['created_at']}")
                if backup.get('created_by'):
                    print(f"   By: {backup['created_by']}")
                if backup.get('statistics'):
                    stats = backup['statistics']
                    print(f"   Documents: {stats.get('total_documents', 0)}")
                    print(f"   Users: {stats.get('total_users', 0)}")
                if backup.get('error'):
                    print(f"   ❌ Error: {backup['error']}")
        
        except Exception as e:
            print(f"❌ Error listing backups: {e}")


def records_status():
    """
    The record process at a glance: the traffic light, and what is stuck.

    Written for somebody on a terminal at seven in the morning who wants to
    know whether yesterday's checks went through, without opening a browser.
    """
    from app.database import SessionLocal, init_db
    from app.models_qms import Format, QualityTeam
    from app.services import record_service as recs
    from app.services import format_service as fmts

    init_db()
    db = SessionLocal()
    try:
        fmts.ensure_teams(db)
        recs.refresh_all_statuses(db)
        stats = recs.stats(db)

        print("\n📋 Record filling & approval")
        print("=" * 52)

        teams = db.query(QualityTeam).order_by(QualityTeam.code).all()
        active = db.query(Format).filter(Format.status == fmts.ACTIVE).count()
        drafts = db.query(Format).filter(Format.status == fmts.DRAFT).count()
        print(f"  Quality teams      {len(teams)}  "
              + ", ".join(t.name for t in teams))
        print(f"  Formats in use     {active}"
              + (f"   ({drafts} still draft)" if drafts else ""))

        print("\n  Status")
        print(f"    🟢 green         {stats['green']:>4}   ok for final review")
        print(f"    🟡 yellow        {stats['yellow']:>4}   filling in progress")
        print(f"    🔴 red           {stats['red']:>4}   needs to reverify with CFT")

        print("\n  Where records are")
        for stage, label in (
            ("filling", "being filled"),
            ("po_approval", "with the Process Owner"),
            ("opo_approval", "with the Overall Process Owner"),
            ("cft_review", "in CFT joint review"),
            ("final_decision", "at the final decision"),
            ("stored", "filed on the server"),
        ):
            print(f"    {label:<32} {stats[stage]:>4}")

        print("\n  Observations")
        print(f"    ok                             {stats['ok']:>4}")
        print(f"    N-ok                           {stats['not_ok']:>4}")
        if stats["nok_open"]:
            print(f"    ⚠️  N-ok flags still open       {stats['nok_open']:>4}"
                  "   waiting on the Overall Process Owner")

        # Formats that cannot be released yet, and why. This is the single most
        # common reason a new installation appears to do nothing.
        blocked = [
            f for f in db.query(Format).filter(Format.status == fmts.DRAFT).all()
            if fmts.readiness(f)
        ]
        if blocked:
            print("\n  ⚠️  Drafts that cannot be released yet")
            for fmt in blocked:
                print(f"    {fmt.code} rev {fmt.revision}")
                for problem in fmts.readiness(fmt):
                    print(f"      - {problem}")

        print()
    finally:
        db.close()


def change_requests_status():
    """Open change requests, and who each one is waiting on."""
    from app.database import SessionLocal, init_db
    from app.services import change_request_service as dcr

    init_db()
    db = SessionLocal()
    try:
        stats = dcr.stats(db)
        print("\n🔁 Change requests")
        print("=" * 52)
        for key, label in (
            ("submitted", "Submitted"),
            ("under_review", "Under review"),
            ("approved", "Approved, awaiting execution"),
            ("implemented", "Implemented"),
            ("rejected", "Not approved"),
        ):
            print(f"  {label:<32} {stats[key]:>4}")

        waiting = [r for r in dcr.list_requests(db)
                   if r.status in dcr.OPEN_STATUSES]
        if waiting:
            print("\n  Waiting on a QMS Coordinator")
            for request in waiting:
                who = (request.coordinator.full_name or request.coordinator.username) \
                    if request.coordinator else "nobody named"
                fmt = f" · {request.format.code}" if request.format else ""
                print(f"    {request.number}{fmt} — {who}")
        print()
    finally:
        db.close()


def main():
    """Main CLI entry point"""
    # Windows consoles still default to a legacy code page, and every command
    # here prints a symbol that is not in it. Without this, `cli.py status` on a
    # stock Windows terminal ends in a UnicodeEncodeError rather than a status
    # report - which is a poor way to meet a new administrator.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # already UTF-8, or not a real tty
            pass

    parser = argparse.ArgumentParser(description="Quality record system CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Init command
    subparsers.add_parser("init", help="Initialize the system")
    
    # Serve command
    subparsers.add_parser("serve", help="Start the web server")
    
    # Status command
    subparsers.add_parser("status", help="Show system status")
    
    # Setup command
    subparsers.add_parser("setup-root", help="Setup root folder")

    # User management
    subparsers.add_parser("users", help="List user accounts")

    reset_parser = subparsers.add_parser(
        "reset-password", help="Set a new password for an account"
    )
    reset_parser.add_argument("username", help="Username or email")
    reset_parser.add_argument(
        "--password", help="New password (prompted for if omitted)"
    )

    # Model configuration commands
    subparsers.add_parser(
        "sync-model-config",
        help="Push config/models.json into the database settings table",
    )
    # Database optimization commands
    db_parser = subparsers.add_parser("db", help="Database management commands")
    db_subparsers = db_parser.add_subparsers(dest="db_command", help="Database operations")
    
    # Index management
    db_subparsers.add_parser("create-indexes", help="Create database indexes for performance")
    db_subparsers.add_parser("analyze", help="Analyze database performance")
    db_subparsers.add_parser("optimize", help="Optimize database (VACUUM, ANALYZE, REINDEX)")
    db_subparsers.add_parser("size", help="Show database size information")
    
    # The record process
    subparsers.add_parser(
        "records", help="Record process status: the traffic light and what is stuck"
    )
    subparsers.add_parser(
        "change-requests", help="Open format change requests and who they wait on"
    )

    # Backup commands
    backup_parser = subparsers.add_parser("backup", help="Backup management commands")
    backup_subparsers = backup_parser.add_subparsers(dest="backup_command", help="Backup operations")
    
    create_backup_parser = backup_subparsers.add_parser("create", help="Create system backup")
    create_backup_parser.add_argument("--name", help="Custom backup name")
    create_backup_parser.add_argument("--no-files", action="store_true", help="Skip file backup")
    
    restore_backup_parser = backup_subparsers.add_parser("restore", help="Restore system backup")
    restore_backup_parser.add_argument("archive", help="Path to backup archive")
    restore_backup_parser.add_argument("--no-files", action="store_true", help="Skip file restore")
    
    backup_subparsers.add_parser("list", help="List available backups")
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_system()
    elif args.command == "serve":
        serve()
    elif args.command == "status":
        status()
    elif args.command == "setup-root":
        setup_root()
    elif args.command == "users":
        list_users()
    elif args.command == "reset-password":
        sys.exit(reset_password(args.username, args.password))
    elif args.command == "sync-model-config":
        sync_model_config()
    elif args.command == "records":
        records_status()
    elif args.command == "change-requests":
        change_requests_status()
    elif args.command == "db":
        handle_db_command(args)
    elif args.command == "backup":
        handle_backup_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
