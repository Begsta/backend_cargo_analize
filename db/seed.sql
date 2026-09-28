INSERT INTO users (user_id, user_login, user_name)
VALUES (1, 'wolff', 'Оператор крана')
ON CONFLICT (user_id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('users', 'user_id'),
    GREATEST((SELECT COALESCE(MAX(user_id), 1) FROM users), 1)
);

INSERT INTO cargos (
    cargo_name,
    cargo_description,
    publication_status,
    image_url,
    video_url,
    cargo_mass,
    cargo_volume,
    created_at,
    formed_at,
    creator_user_id
)
SELECT *
FROM (
    VALUES
        (
            'Панель перекрытия ПБ 62.12-8',
            'Подъём ЖБ-панели башенным краном WOLFF.',
            'published',
            '',
            '',
            4,
            2,
            NOW(),
            NOW(),
            1
        ),
        (
            'Балка железобетонная Б-1 60',
            'Монтажная балка для каркаса.',
            'published',
            '',
            '',
            7,
            3,
            NOW(),
            NOW(),
            1
        ),
        (
            'Фундаментный блок ФБС 24.6.6',
            'Блок стен подвала.',
            'published',
            '',
            '',
            2,
            1,
            NOW(),
            NOW(),
            1
        )
) AS seed (
    cargo_name,
    cargo_description,
    publication_status,
    image_url,
    video_url,
    cargo_mass,
    cargo_volume,
    created_at,
    formed_at,
    creator_user_id
)
WHERE NOT EXISTS (SELECT 1 FROM cargos);
