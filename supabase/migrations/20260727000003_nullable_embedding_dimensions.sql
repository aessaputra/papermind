-- Allow auto-detect (NULL) for embedding dimensions. NULL means "omit the
-- dimensions param and let the provider use the model default".
ALTER TABLE public.user_embedding_configs
    ALTER COLUMN embedding_dimensions DROP NOT NULL;
ALTER TABLE public.user_embedding_configs
    ALTER COLUMN embedding_dimensions DROP DEFAULT;
