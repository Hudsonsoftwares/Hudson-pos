@echo off
echo Restarting Odoo 20.0 Windows Service...
net stop odoo-server-20.0
net start odoo-server-20.0
echo Done! Odoo service has been restarted.
pause
