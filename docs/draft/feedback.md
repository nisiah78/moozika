Retour sur le partition @docs/solfege/heavy/jubilate-deo-peter-anglea.pdf :
- m1 1er temps, note fausse, c'est m au lieu de s', m1 9em temps, note remonté ,0 sur soprano, vraie note : s:- ,
- m61 entier est vide pour les voix => voir l'original docs/solfege/heavy/original.png  
- la note du m62 dans l'original est manquant dans le note parsé, c'est directement le note du m63 original qui est sur la m62.
- a partir du mesure 63 tout les notes sont fausse et certain voix chante une partie de l'autre 
ex: m63 (original), soprano 1 et 2 avec deux note different, dans le note parsé, le soprano 2 n'as pas de note sur le m64 3 dernier temps, alors que le alto est 1 voix uniquement mais sur le note parsé, il y a alto 1 et alto 2 avec chacun leur propre note, dont je ne sais pas quelle note sur la partition en tontalité B

document: 
le retour de l'api 
http://localhost:3000/api/pdf/parse/stream avec status done est dans @docs/solfege/heavy/parsed.json
