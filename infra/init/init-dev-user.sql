-- Initialize development user and workspace
-- This script creates the default dev user and workspace for local development

-- Insert development user
INSERT INTO users (
    id,
    email,
    name,
    first_name,
    last_name,
    auth_provider,
    roles,
    is_active,
    created_at,
    updated_at
) VALUES (
    '550e8400-e29b-41d4-a716-446655440000'::uuid,
    'dev@primedata.local',
    'Development User',
    'Development',
    'User',
    'NONE',
    '["owner", "admin"]'::jsonb,
    true,
    NOW(),
    NOW()
) ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    auth_provider = EXCLUDED.auth_provider,
    is_active = true,
    updated_at = NOW();

-- Insert development workspace
INSERT INTO workspaces (
    id,
    name,
    created_at,
    updated_at
) VALUES (
    '550e8400-e29b-41d4-a716-446655440001'::uuid,
    'Default Development Workspace',
    NOW(),
    NOW()
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    updated_at = NOW();

-- Link user to workspace as owner
INSERT INTO workspace_members (
    id,
    workspace_id,
    user_id,
    role,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    '550e8400-e29b-41d4-a716-446655440001'::uuid,
    '550e8400-e29b-41d4-a716-446655440000'::uuid,
    'OWNER',
    NOW(),
    NOW()
) ON CONFLICT (workspace_id, user_id) DO UPDATE SET
    role = 'OWNER',
    updated_at = NOW();

-- Create billing profile for workspace (FREE plan by default)
INSERT INTO billing_profiles (
    workspace_id,
    plan,
    usage,
    created_at,
    updated_at
) VALUES (
    '550e8400-e29b-41d4-a716-446655440001'::uuid,
    'FREE',
    '{}'::jsonb,
    NOW(),
    NOW()
) ON CONFLICT (workspace_id) DO UPDATE SET
    updated_at = NOW();

