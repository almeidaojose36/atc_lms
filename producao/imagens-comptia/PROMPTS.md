# Imagens para as amostras CompTIA A+ e Network+

Imagens originais para os manuais, as apresentações e o vídeo de demonstração do A+. Gere-as com a sua ferramenta de imagens e grave-as com o **nome de ficheiro indicado** em:

- A+: `cursos/comptia-a-plus/manual/figures/`
- Network+: `cursos/comptia-network-plus/manual/figures/`

Depois, eu ligo cada imagem à secção certa do manual, volto a gerar as apresentações e monto o vídeo de demonstração do A+ (animação, locução da Helena ou do Miguel e legendas). **Não precisa de animar nada.**

## Regras para todas as imagens

- **16:9, 1920 × 1080 ou maior.**
- **Sem texto na imagem.** Os títulos e as legendas são acrescentados pela plataforma, em português. (As ferramentas de imagem escrevem mal; texto errado num curso parece pouco profissional.)
- **Sem logótipos de marcas** (Apple, Samsung, Dell, Cisco, PowerCert, etc.) e sem cópias de imagens de outros cursos.
- Estilo ATC: fundo azul-marinho **#0B2137**, destaques laranja **#DA6D24**, luz suave de estúdio, aspeto fotográfico limpo e realista.
- Quando aparece uma pessoa: use os retratos da Helena e do Miguel como referência (`static/presenters/helena.png`, `static/presenters/miguel.png`), com polo azul-marinho e o emblema ATC no peito, para ficarem iguais aos vídeos. Gere **duas versões** (`-helena` e `-miguel`): a plataforma mostra a do guia que o formando escolheu.

Acrescente a cada prompt, no fim:

> Clean, photorealistic educational illustration, soft studio lighting, deep navy blue background (#0B2137) with subtle orange (#DA6D24) accent lights, high detail, no text, no letters, no logos, no watermarks, 16:9.

---

## CompTIA A+ · Módulo 1 · Dispositivos móveis

| # | Ficheiro | Secção | Prompt |
|---|---|---|---|
| A1 | `aplus-seguranca-helena.jpg` / `aplus-seguranca-miguel.jpg` | 1.1 Antes de abrir um portátil | A young Angolan IT technician (Helena / Miguel, navy polo shirt with an ATC badge) seated at a clean repair bench, wearing a blue anti-static wrist strap clipped to a grounding point, a closed laptop lying upside down on an orange anti-static mat, a small magnetic tray with screws neatly sorted, a precision screwdriver set beside it. Calm, careful posture. |
| A2 | `aplus-ram-sodimm.jpg` | 1.2 Memória RAM | Close-up of hands inserting a SO-DIMM laptop memory module at a 30-degree angle into an open laptop's memory slot, the two metal retaining clips visible on each side, the notch on the module aligned with the slot key, shallow depth of field. |
| A3 | `aplus-ram-comparacao.jpg` | 1.2 Memória RAM | Product-style comparison shot: a long desktop DIMM memory module above a shorter laptop SO-DIMM module, both green circuit boards with black memory chips, lying flat on a navy surface, evenly lit from above. |
| A4 | `aplus-interior-portatil.jpg` | 1.3 Armazenamento e placa sem fios | Top-down view of an opened generic laptop (no brand) showing the motherboard: an M.2 NVMe SSD stick, an empty 2.5-inch drive bay with a SATA connector, a small M.2 wireless card with two thin antenna cables (one black, one grey) attached, the battery connector unplugged. Subtle orange glow outlining the SSD and the wireless card. |
| A5 | `aplus-ssd-formatos.jpg` | 1.3 Armazenamento e placa sem fios | Three storage devices side by side on a navy surface: a 2.5-inch SATA SSD in a metal case, an M.2 SATA SSD and a longer M.2 NVMe SSD (2280 size), showing the different key notches on the connectors. Product photography. |
| A6 | `aplus-bluetooth-helena.jpg` / `aplus-bluetooth-miguel.jpg` | 1.4 Emparelhar acessórios Bluetooth | Helena / Miguel (navy ATC polo) holding a generic smartphone (no brand) next to an open charging case with white wireless earbuds whose status light blinks blue; a soft orange wave between the phone and the earbuds suggests pairing. Waist-up, friendly expression, office background softly blurred. |
| A7 | `aplus-hotspot.jpg` | 1.5 Ligações dos dispositivos móveis | A generic smartphone standing on a desk sharing its mobile connection with a nearby laptop: soft orange Wi-Fi arcs flow from the phone to the laptop; a USB-C cable lies coiled beside them as the tethering alternative. Modern African office setting, evening light. |
| A8 | `aplus-docking.jpg` | 1.5 Ligações dos dispositivos móveis | A generic laptop connected with a single USB-C cable to a small docking station, which connects to an external monitor, a keyboard, a mouse and a network cable on a tidy desk. |
| A9 | `aplus-sincronizacao.jpg` | 1.6 Sincronização | A generic smartphone and a laptop on a desk, both showing the same simple inbox layout without readable text; a glowing orange cloud icon floats between them with two circular arrows, suggesting synchronization of e-mail, contacts and calendar. |
| A10 | `aplus-capa.jpg` | Capa do vídeo e da apresentação | Wide hero image: an organized repair workstation at night with an opened laptop, a smartphone, wireless earbuds, a memory module and an SSD arranged in a neat flat-lay on a navy mat, orange rim light. Leave the left third of the image empty and dark for a title. |

## CompTIA Network+ · Módulo 1 · Conceitos de redes

| # | Ficheiro | Secção | Prompt |
|---|---|---|---|
| N1 | `netplus-topologia-estrela.jpg` | 1.1 O que é uma rede? | Isometric illustration of a small office network in a star topology: six desks with computers and a printer, each connected by glowing orange cables to one central network switch in a wall cabinet; a wireless access point on the ceiling with soft signal rings. Clean 3D style on navy background. |
| N2 | `netplus-tipos-rede.jpg` | 1.1 O que é uma rede? | Four concentric scales in one image: a single office building (LAN), the same building with Wi-Fi rings (WLAN), several buildings across a city connected by fibre lines (MAN), and the globe with glowing links between continents (WAN). Isometric 3D, navy and orange. |
| N3 | `netplus-osi-camadas.jpg` | 1.2 O modelo OSI | Seven horizontal translucent glass layers stacked vertically like a tower, each slightly different shade from orange at the top to navy at the bottom, a small glowing data packet travelling down through the layers and turning into light pulses on a cable at the bottom. Abstract 3D, no text. |
| N4 | `netplus-nat-router.jpg` | 1.3 Endereçamento IPv4 | A home/office router in the centre; on the left, three devices (laptop, phone, desktop) inside a softly lit house outline representing the private network; on the right, a single glowing line going out to a stylized globe representing the Internet. Orange light flows through the router. |
| N5 | `netplus-dhcp-dora.jpg` | 1.4 DHCP e DNS | A desktop computer on the left and a server rack on the right with orange status lights; four arcs of light travel between them, alternating direction (left→right, right→left, left→right, right→left), representing the four DHCP messages. Clean 3D illustration. |
| N6 | `netplus-dns.jpg` | 1.4 DHCP e DNS | A person's hand typing on a laptop; from the screen, a beam goes to a server shaped like an address book, which returns a glowing numeric-looking code (abstract dots, no readable numbers) back to the laptop. |
| N7 | `netplus-portas.jpg` | 1.5 Portas e protocolos | A large server drawn as a building with many small numbered-looking doors (no readable numbers), each door glowing in a different colour; data envelopes and small padlocks approach specific doors along orange light paths. Playful but professional 3D. |
| N8 | `netplus-equipamentos.jpg` | 1.6 Equipamentos de rede | Product line-up on a navy surface: a 24-port network switch, a router with antennas, a ceiling-mount wireless access point and a firewall appliance, all generic and unbranded, evenly lit, small orange status LEDs. |
| N9 | `netplus-tecnico-helena.jpg` / `netplus-tecnico-miguel.jpg` | Exercício prático | Helena / Miguel (navy ATC polo) at a desk running the command line on a laptop (screen shows abstract white lines on black, no readable text), a network cable plugged into the laptop, focused and smiling. |
| N10 | `netplus-capa.jpg` | Capa da apresentação | Wide hero image of a server room corridor with racks on both sides, orange and navy lighting, glowing network cables converging towards the vanishing point; left third darker and empty for a title. |

---

### Notas

- Os retratos de referência servem para manter o mesmo rosto. Se a ferramenta não aceitar imagens de referência, descreva: *young Angolan woman, long dark braids, warm smile* (Helena) ou *young Angolan man, short hair, clean-shaven, friendly smile* (Miguel).
- Se uma imagem sair com texto, letras ou logótipos, peça uma nova versão em vez de a editar.
- As imagens do A+ que já existem em `A+ PT Images/` não devem ser usadas: são fotogramas de um curso de terceiros (PowerCert), apenas traduzidos.
