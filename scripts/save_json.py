import os
import json
import sys

from i18n.i18n import I18nAuto

i18n = I18nAuto()


def save_viral_segments(segments_data=None, project_folder="tmp", overwrite=False):
    output_txt_file = os.path.join(project_folder, "viral_segments.txt")

    # Sobrescrita explícita (usado pelo filtro de segurança)
    if overwrite and segments_data is not None:
        with open(output_txt_file, 'w', encoding='utf-8') as file:
            json.dump(segments_data, file, ensure_ascii=False, indent=4)
        print(i18n("Viral segments saved to {}").format(output_txt_file) + "\n")
        return

    # Verifica se o arquivo já existe
    if not os.path.exists(output_txt_file):
        if segments_data is None:
            # Never block automation: without an interactive terminal there
            # is nobody to answer the prompt, so skip instead of hanging.
            if not sys.stdin.isatty():
                print(i18n("No segments data provided and no interactive input available. Skipping save."))
                return
            # Solicita ao usuário que insira o JSON caso o arquivo não exista e os segmentos não estejam definidos
            while True:
                user_input = input(i18n("\nPlease enter the JSON in the desired format:\n"))
                try:
                    # Tenta carregar o JSON inserido
                    segments_data = json.loads(user_input)

                    # Valida se o formato está correto
                    if "segments" in segments_data and isinstance(segments_data["segments"], list):
                        # Salva os dados em um arquivo JSON
                        with open(output_txt_file, 'w', encoding='utf-8') as file:
                            json.dump(segments_data, file, ensure_ascii=False, indent=4)
                        print(i18n("Viral segments saved to {}").format(output_txt_file))
                        break
                    else:
                        print(i18n("Invalid format. Make sure the structure is correct."))
                except json.JSONDecodeError:
                    print(i18n("Error decoding JSON. Please check the formatting."))
                print(i18n("Please try again."))
        else:
            # Caso os segmentos tenham sido gerados, salva automaticamente
            with open(output_txt_file, 'w', encoding='utf-8') as file:
                json.dump(segments_data, file, ensure_ascii=False, indent=4)
            print(i18n("Viral segments saved to {}").format(output_txt_file) + "\n")
    else:
        print(i18n("The file {} already exists. No additional input needed.").format(output_txt_file))
