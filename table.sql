-- Table: public.logs

-- DROP TABLE IF EXISTS public.logs;

CREATE TABLE IF NOT EXISTS public.logs
(
    id integer NOT NULL DEFAULT nextval('logs_id_seq'::regclass),
    domain text COLLATE pg_catalog."default" NOT NULL,
    uri text COLLATE pg_catalog."default" NOT NULL,
    email text COLLATE pg_catalog."default",
    password text COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT logs_pkey PRIMARY KEY (id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.logs
    OWNER to root;
-- Index: idx_logs_domain_trgm

-- DROP INDEX IF EXISTS public.idx_logs_domain_trgm;

CREATE INDEX IF NOT EXISTS idx_logs_domain_trgm
    ON public.logs USING gin
    (domain COLLATE pg_catalog."default" gin_trgm_ops)
    TABLESPACE pg_default;
-- Index: idx_logs_email_trgm

-- DROP INDEX IF EXISTS public.idx_logs_email_trgm;

CREATE INDEX IF NOT EXISTS idx_logs_email_trgm
    ON public.logs USING gin
    (email COLLATE pg_catalog."default" gin_trgm_ops)
    TABLESPACE pg_default;
-- Index: idx_logs_password_trgm

-- DROP INDEX IF EXISTS public.idx_logs_password_trgm;

CREATE INDEX IF NOT EXISTS idx_logs_password_trgm
    ON public.logs USING gin
    (password COLLATE pg_catalog."default" gin_trgm_ops)
    TABLESPACE pg_default;
