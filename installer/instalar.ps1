# STEH Chip-Assigner - Instalador con interfaz grafica
# Requiere PowerShell 5+ y permisos de administrador

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$INSTALL_DIR   = "C:\STEH\chip-assigner"
$EXE_NAME      = "ChipAssigner.exe"
$STARTUP_DIR   = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$SHORTCUT_PATH = "$STARTUP_DIR\STEH-ChipAssigner.lnk"
$CONFIG_PATH   = "$INSTALL_DIR\config.json"
$SCRIPT_DIR    = Split-Path -Parent $MyInvocation.MyCommand.Path
$DIST_DIR      = Join-Path (Split-Path -Parent $SCRIPT_DIR) "dist"
$INF_PATH      = Join-Path $SCRIPT_DIR "driver\yr9011.inf"
$YR9011_VID    = "04E8"
$YR9011_PID    = "20E4"

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

function Show-Message($title, $msg, $icon = "Information") {
    [System.Windows.Forms.MessageBox]::Show(
        $msg, $title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::$icon
    ) | Out-Null
}

function Get-ComPorts {
    Get-WmiObject Win32_PnPEntity |
        Where-Object { $_.Name -match "COM\d+" } |
        ForEach-Object {
            if ($_.Name -match "COM(\d+)") {
                [PSCustomObject]@{ Name = $_.Name; Port = "COM$($Matches[1])" }
            }
        }
}

function Find-YR9011Port {
    $devices = Get-WmiObject Win32_PnPEntity |
        Where-Object { $_.DeviceID -like "*VID_$YR9011_VID*PID_$YR9011_PID*" }
    if ($devices) {
        $name = $devices[0].Name
        if ($name -match "COM(\d+)") { return "COM$($Matches[1])" }
    }
    return $null
}

# ------------------------------------------------------------------ #
# Ventana de progreso                                                  #
# ------------------------------------------------------------------ #

$form = New-Object System.Windows.Forms.Form
$form.Text            = "STEH Chip-Assigner - Instalacion"
$form.Size            = New-Object System.Drawing.Size(480, 320)
$form.StartPosition   = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox     = $false
$form.MinimizeBox     = $false

$logo = New-Object System.Windows.Forms.Label
$logo.Text      = "STEH Chip-Assigner"
$logo.Font      = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$logo.Location  = New-Object System.Drawing.Point(20, 20)
$logo.Size      = New-Object System.Drawing.Size(440, 30)
$form.Controls.Add($logo)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text      = "Instalando el servicio de asignacion de chips RFID..."
$subtitle.Font      = New-Object System.Drawing.Font("Segoe UI", 9)
$subtitle.ForeColor = [System.Drawing.Color]::Gray
$subtitle.Location  = New-Object System.Drawing.Point(20, 55)
$subtitle.Size      = New-Object System.Drawing.Size(440, 20)
$form.Controls.Add($subtitle)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text     = ""
$statusLabel.Font     = New-Object System.Drawing.Font("Segoe UI", 9)
$statusLabel.Location = New-Object System.Drawing.Point(20, 90)
$statusLabel.Size     = New-Object System.Drawing.Size(440, 20)
$form.Controls.Add($statusLabel)

$progressBar = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(20, 120)
$progressBar.Size     = New-Object System.Drawing.Size(440, 22)
$progressBar.Minimum  = 0
$progressBar.Maximum  = 100
$progressBar.Value    = 0
$form.Controls.Add($progressBar)

$logBox = New-Object System.Windows.Forms.ListBox
$logBox.Location  = New-Object System.Drawing.Point(20, 155)
$logBox.Size      = New-Object System.Drawing.Size(440, 100)
$logBox.Font      = New-Object System.Drawing.Font("Consolas", 8)
$logBox.BackColor = [System.Drawing.Color]::FromArgb(240, 240, 240)
$form.Controls.Add($logBox)

function Update-UI($step, $pct, $msg) {
    $statusLabel.Text  = $step
    $progressBar.Value = $pct
    $logBox.Items.Add($msg) | Out-Null
    $logBox.SelectedIndex = $logBox.Items.Count - 1
    $form.Refresh()
    [System.Windows.Forms.Application]::DoEvents()
}

$form.Show()
$form.Refresh()

# ------------------------------------------------------------------ #
# Paso 1 - Instalar driver                                             #
# ------------------------------------------------------------------ #

Update-UI "Paso 1/4 - Instalando driver..." 10 "Instalando driver del YR9011..."

if (Test-Path $INF_PATH) {
    $null = & pnputil /add-driver $INF_PATH /install 2>&1
    Update-UI "Paso 1/4 - Instalando driver..." 20 "Driver registrado en Windows."
} else {
    Update-UI "Paso 1/4 - Instalando driver..." 20 "AVISO: archivo .inf no encontrado, omitiendo."
}

# ------------------------------------------------------------------ #
# Paso 2 - Copiar archivos                                             #
# ------------------------------------------------------------------ #

Update-UI "Paso 2/4 - Copiando archivos..." 30 "Copiando a $INSTALL_DIR..."

if (-not (Test-Path $INSTALL_DIR)) {
    New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
}

$exeSource = Join-Path $DIST_DIR $EXE_NAME
if (Test-Path $exeSource) {
    Copy-Item $exeSource $INSTALL_DIR -Force
    Update-UI "Paso 2/4 - Copiando archivos..." 40 "Archivos copiados correctamente."
} else {
    Update-UI "Paso 2/4 - Copiando archivos..." 40 "AVISO: .exe no encontrado en $exeSource"
}

# ------------------------------------------------------------------ #
# Paso 3 - Detectar puerto YR9011                                      #
# ------------------------------------------------------------------ #

Update-UI "Paso 3/4 - Buscando lector YR9011..." 50 "Buscando lector por VID/PID..."

# Pedir siempre que conecte el dispositivo antes de detectar
[System.Windows.Forms.MessageBox]::Show(
    "Antes de continuar:`r`n`r`n1. Conecte el lector YR9011 al puerto USB`r`n2. Espere 5 segundos`r`n3. Haga clic en Aceptar",
    "Conecte el lector YR9011",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null

$selectedPort = Find-YR9011Port

if ($selectedPort) {
    Update-UI "Paso 3/4 - Lector encontrado" 65 "YR9011 detectado automaticamente en $selectedPort"
} else {
    Update-UI "Paso 3/4 - Seleccion manual" 55 "No se detecto automaticamente. Seleccion manual..."
    $form.Refresh()

    $portForm = New-Object System.Windows.Forms.Form
    $portForm.Text            = "Seleccionar puerto del lector"
    $portForm.Size            = New-Object System.Drawing.Size(420, 240)
    $portForm.StartPosition   = "CenterScreen"
    $portForm.FormBorderStyle = "FixedDialog"
    $portForm.MaximizeBox     = $false

    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text     = "El lector no se detecto automaticamente.`r`n`r`nSeleccione el puerto COM al que lo conecto`r`no haga clic en Actualizar si recien lo conecto:"
    $lbl.Location = New-Object System.Drawing.Point(15, 15)
    $lbl.Size     = New-Object System.Drawing.Size(380, 60)
    $portForm.Controls.Add($lbl)

    $combo = New-Object System.Windows.Forms.ComboBox
    $combo.Location      = New-Object System.Drawing.Point(15, 85)
    $combo.Size          = New-Object System.Drawing.Size(260, 25)
    $combo.DropDownStyle = "DropDownList"
    foreach ($p in (Get-ComPorts)) { $combo.Items.Add($p.Name) | Out-Null }
    if ($combo.Items.Count -gt 0) { $combo.SelectedIndex = 0 }
    $portForm.Controls.Add($combo)

    $refreshBtn = New-Object System.Windows.Forms.Button
    $refreshBtn.Text     = "Actualizar"
    $refreshBtn.Location = New-Object System.Drawing.Point(285, 84)
    $refreshBtn.Size     = New-Object System.Drawing.Size(110, 26)
    $refreshBtn.Add_Click({
        $combo.Items.Clear()
        # Intentar auto-detectar primero
        $autoPort = Find-YR9011Port
        foreach ($p in (Get-ComPorts)) { $combo.Items.Add($p.Name) | Out-Null }
        if ($autoPort) {
            # Seleccionar el YR9011 si se detecto
            for ($i = 0; $i -lt $combo.Items.Count; $i++) {
                if ($combo.Items[$i] -match $autoPort) { $combo.SelectedIndex = $i; break }
            }
        } elseif ($combo.Items.Count -gt 0) {
            $combo.SelectedIndex = 0
        }
    })
    $portForm.Controls.Add($refreshBtn)

    $okBtn = New-Object System.Windows.Forms.Button
    $okBtn.Text         = "Confirmar"
    $okBtn.Location     = New-Object System.Drawing.Point(15, 150)
    $okBtn.Size         = New-Object System.Drawing.Size(100, 30)
    $okBtn.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $portForm.Controls.Add($okBtn)

    $skipBtn = New-Object System.Windows.Forms.Button
    $skipBtn.Text         = "Omitir"
    $skipBtn.Location     = New-Object System.Drawing.Point(125, 150)
    $skipBtn.Size         = New-Object System.Drawing.Size(100, 30)
    $skipBtn.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $portForm.Controls.Add($skipBtn)

    $portForm.AcceptButton = $okBtn

    if ($portForm.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK -and $combo.SelectedItem) {
        if ($combo.SelectedItem.ToString() -match "COM(\d+)") {
            $selectedPort = "COM$($Matches[1])"
            Update-UI "Paso 3/4 - Puerto seleccionado" 65 "Puerto seleccionado: $selectedPort"
        }
    } else {
        Update-UI "Paso 3/4 - Sin puerto" 65 "Omitido. El servicio intentara detectarlo al iniciar."
    }
}

if ($selectedPort -and (Test-Path $CONFIG_PATH)) {
    $config = Get-Content $CONFIG_PATH -Raw | ConvertFrom-Json
    $config.serial_port = $selectedPort
    $config | ConvertTo-Json | Set-Content $CONFIG_PATH -Encoding UTF8
    Update-UI "Paso 3/4 - Config guardada" 70 "config.json actualizado: $selectedPort"
}

# ------------------------------------------------------------------ #
# Paso 4 - Inicio automatico y arranque                                #
# ------------------------------------------------------------------ #

Update-UI "Paso 4/4 - Configurando inicio automatico..." 80 "Creando acceso directo en Startup..."

$exeDest = Join-Path $INSTALL_DIR $EXE_NAME
$ws      = New-Object -ComObject WScript.Shell
$sc      = $ws.CreateShortcut($SHORTCUT_PATH)
$sc.TargetPath       = $exeDest
$sc.WorkingDirectory = $INSTALL_DIR
$sc.Description      = "STEH Chip-Assigner"
$sc.WindowStyle      = 7
$sc.Save()

Update-UI "Paso 4/4 - Iniciando servicio..." 90 "Lanzando ChipAssigner..."

if (Test-Path $exeDest) {
    Start-Process $exeDest -WorkingDirectory $INSTALL_DIR
    Start-Sleep -Seconds 2
    Update-UI "Completado" 100 "Servicio iniciado. Revise el icono en la bandeja del sistema."
} else {
    Update-UI "Aviso" 95 "No se encontro el .exe. Verifique la carpeta dist\."
}

$form.Close()

# ------------------------------------------------------------------ #
# Cartel final                                                         #
# ------------------------------------------------------------------ #

$portMsg = if ($selectedPort) { "Puerto configurado: $selectedPort" } else { "Puerto: no configurado (editar config.json)" }

Show-Message "Instalacion completada" @"
STEH Chip-Assigner instalado correctamente.

  Driver YR9011 registrado
  Archivos copiados a C:\STEH\chip-assigner\
  Inicio automatico con Windows configurado
  Servicio iniciado

$portMsg

El servicio arrancara automaticamente al iniciar
sesion en Windows. Revise el icono en la bandeja
del sistema (esquina inferior derecha).
"@
