DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';
SELECT COUNT(*) AS remaining FROM ir_attachment WHERE url LIKE '/web/assets/%';
