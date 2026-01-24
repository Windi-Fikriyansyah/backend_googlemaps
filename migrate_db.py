def migrate():
    print("Starting migration...")
    with engine.connect() as conn:
        try:
            # 1. Create association table if not exists
            print("Creating 'search_leads' association table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS search_leads (
                    search_id INTEGER REFERENCES searches(id) ON DELETE CASCADE,
                    lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                    PRIMARY KEY (search_id, lead_id)
                )
            """))

            # 2. Add columns to searches table
            print("Updating 'searches' table columns...")
            conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS keyword VARCHAR"))
            conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS location_name VARCHAR"))
            conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS radius FLOAT"))
            conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS max_results INTEGER DEFAULT 20"))
            
            # 3. Handle data migration from Leads.search_id to SearchLeads table
            # Check if search_id column exists in leads table
            print("Migrating existing lead associations...")
            try:
                # This moves existing relationships to the join table
                conn.execute(text("""
                    INSERT INTO search_leads (search_id, lead_id)
                    SELECT search_id, id FROM leads 
                    WHERE search_id IS NOT NULL
                    ON CONFLICT DO NOTHING
                """))
                # Optionally drop the column after migration in a real scenario
                # conn.execute(text("ALTER TABLE leads DROP COLUMN search_id"))
            except Exception as e:
                print(f"Info: Could not migrate from search_id (maybe already deleted): {e}")

            conn.commit()
            print("Migration completed successfully!")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
